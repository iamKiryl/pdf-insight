"""FastAPI application: POST /api/analyze and GET /api/health."""

import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .analyzer import ModelUsage, analyze
from .chunk_prompt import CHUNK_PROMPT_VERSION
from .chunked import ChunkedStats, analyze_chunked
from .compact import COMPACT_MAX_CHARS, COMPACT_PROMPT_VERSION, analyze_compact
from .config import Settings
from .contract import MAX_TOTAL_CHARS, MIN_TOTAL_LETTERS, SINGLE_CALL_MAX_CHARS, AnalyzeRequest
from .errors import ApiError
from .logs import log_event
from .middleware import BodyLimitMiddleware, CorsMiddleware
from .prompt import PROMPT_VERSION
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


def _parse_request(body: bytes, settings: Settings) -> AnalyzeRequest:
    try:
        data: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError("INVALID_REQUEST") from None
    try:
        request = AnalyzeRequest.model_validate(data)
    except ValidationError:
        raise ApiError("INVALID_REQUEST") from None
    limit = {"single": SINGLE_CALL_MAX_CHARS, "compact": COMPACT_MAX_CHARS}.get(
        settings.ai_mode, MAX_TOTAL_CHARS
    )
    if request.total_chars > limit:
        raise ApiError("DOCUMENT_TOO_LONG")  # explicit; text is never truncated
    if len(request.pagesWithoutText) == request.pageCount:
        raise ApiError("NO_TEXT_LAYER")
    if request.ocrPages and settings.ai_mode != "compact":
        raise ApiError("INVALID_REQUEST")  # only compact tells the model which text is OCR
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
            "mode": runtime.settings.ai_mode,
        }

    @api.post("/api/analyze")
    async def analyze_document(request: Request) -> JSONResponse:
        started = time.monotonic()
        runtime = runtime_factory(request.scope)
        fields: dict[str, Any] = {
            "event": "analyze",
            "model": runtime.settings.ai_model,
            "promptVersion": {
                "compact": COMPACT_PROMPT_VERSION,
                "chunked": CHUNK_PROMPT_VERSION,
            }.get(runtime.settings.ai_mode, PROMPT_VERSION),
        }
        usage = ModelUsage()
        chunk = ChunkedStats()
        fields["mode"] = runtime.settings.ai_mode
        try:
            await _enforce_rate_limit(runtime, request.headers.get("cf-connecting-ip", "unknown"))
            parsed = _parse_request(await request.body(), runtime.settings)
            fields |= {
                "pageCount": parsed.pageCount,
                "pagesWithoutText": len(parsed.pagesWithoutText),
                "ocrPages": len(parsed.ocrPages),
                "textChars": parsed.total_chars,
            }
            if runtime.ai is None:
                raise ApiError("SERVICE_MISCONFIGURED")
            if runtime.settings.ai_mode == "chunked":
                outcome = await analyze_chunked(parsed, runtime.ai, runtime.settings, usage, chunk)
            elif runtime.settings.ai_mode == "compact":
                outcome = await analyze_compact(parsed, runtime.ai, runtime.settings, usage)
            else:
                outcome = await analyze(parsed, runtime.ai, runtime.settings, usage)
        except ApiError as exc:
            fields |= usage.log_fields() | _chunk_fields(runtime.settings, chunk)
            log_event(**fields, outcome=exc.code, status=exc.spec.status, ms=_ms(started))
            return _error_response(exc)
        except Exception:
            fields |= usage.log_fields() | _chunk_fields(runtime.settings, chunk)
            log_event(**fields, outcome="INTERNAL_ERROR", status=500, ms=_ms(started))
            return _error_response(ApiError("INTERNAL_ERROR"))
        fields |= usage.log_fields() | _chunk_fields(runtime.settings, chunk)
        log_event(**fields, outcome="ok", status=200, attempts=outcome.attempts, ms=_ms(started))
        return JSONResponse(outcome.result.model_dump(mode="json"))

    app: Any = BodyLimitMiddleware(api, runtime_factory)
    return CorsMiddleware(app, runtime_factory)


def _chunk_fields(settings: Settings, stats: ChunkedStats) -> dict[str, int]:
    if settings.ai_mode != "chunked":
        return {}
    return {
        "chunks": stats.chunks,
        "duplicateFacts": stats.duplicate_facts,
    }


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
