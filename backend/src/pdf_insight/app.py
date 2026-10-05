"""FastAPI application: POST /api/analyze and GET /api/health."""

import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .analyzer import analyze
from .contract import MAX_TOTAL_CHARS, MIN_TOTAL_LETTERS, AnalyzeRequest
from .errors import ApiError
from .logs import log_event
from .middleware import BodyLimitMiddleware, CorsMiddleware
from .runtime import Runtime, RuntimeFactory


def _error_response(exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.spec.status)


async def _enforce_rate_limit(runtime: Runtime, client_key: str) -> None:
    limiters = (runtime.ip_limiter, runtime.global_limiter)
    if any(limiter is None for limiter in limiters):
        if runtime.settings.is_production:
            raise ApiError("SERVICE_MISCONFIGURED")
        return  # development without bindings: explicitly unlimited, reported by /api/health
    try:
        allowed_ip = await runtime.ip_limiter.allow(f"ip:{client_key}")  # type: ignore[union-attr]
        allowed_global = allowed_ip and await runtime.global_limiter.allow("global")  # type: ignore[union-attr]
    except Exception:
        raise ApiError("SERVICE_MISCONFIGURED") from None  # fail closed if the limiter breaks
    if not allowed_global:
        raise ApiError("RATE_LIMITED")


def _parse_request(body: bytes) -> AnalyzeRequest:
    try:
        data: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError("INVALID_REQUEST") from None
    try:
        request = AnalyzeRequest.model_validate(data)
    except ValidationError:
        raise ApiError("INVALID_REQUEST") from None
    if request.total_chars > MAX_TOTAL_CHARS:
        raise ApiError("DOCUMENT_TOO_LONG")
    if len(request.pagesWithoutText) == request.pageCount:
        raise ApiError("NO_TEXT_LAYER")
    if request.total_letters < MIN_TOTAL_LETTERS:
        raise ApiError("INSUFFICIENT_CONTENT")
    return request


def create_app(runtime_factory: RuntimeFactory) -> Any:
    # redirect_slashes=False: "/api/analyze/" is a plain 404, never a redirect that re-sends a body.
    api = FastAPI(
        title="PDF Insight API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )

    @api.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc)

    @api.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        runtime = runtime_factory(request.scope)
        return {
            "status": "ok",
            "environment": runtime.settings.environment,
            "aiBinding": runtime.ai is not None,
            "rateLimiter": runtime.ip_limiter is not None and runtime.global_limiter is not None,
        }

    @api.post("/api/analyze")
    async def analyze_document(request: Request) -> JSONResponse:
        started = time.monotonic()
        runtime = runtime_factory(request.scope)
        fields: dict[str, Any] = {"event": "analyze"}
        try:
            await _enforce_rate_limit(runtime, request.headers.get("cf-connecting-ip", "unknown"))
            parsed = _parse_request(await request.body())
            fields |= {
                "pageCount": parsed.pageCount,
                "pagesWithoutText": len(parsed.pagesWithoutText),
                "textChars": parsed.total_chars,
            }
            if runtime.ai is None:
                raise ApiError("SERVICE_MISCONFIGURED")
            outcome = await analyze(parsed, runtime.ai, runtime.settings)
        except ApiError as exc:
            log_event(**fields, outcome=exc.code, status=exc.spec.status, ms=_ms(started))
            return _error_response(exc)
        except Exception:
            log_event(**fields, outcome="INTERNAL_ERROR", status=500, ms=_ms(started))
            return _error_response(ApiError("INTERNAL_ERROR"))
        log_event(**fields, outcome="ok", status=200, attempts=outcome.attempts, ms=_ms(started))
        return JSONResponse(outcome.result.model_dump(mode="json"))

    app: Any = BodyLimitMiddleware(api, runtime_factory)
    return CorsMiddleware(app, runtime_factory)


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
