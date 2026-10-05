"""Cloudflare adapters (with fake bindings) and the streamed body limit at the ASGI level."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from pdf_insight.cloudflare import WorkersAIClient, WorkersRateLimiter, runtime_from_scope
from pdf_insight.config import load_settings
from pdf_insight.middleware import BodyLimitMiddleware, body_precheck, read_limited
from pdf_insight.runtime import AIProviderError, Runtime, classify_provider_error


class FailingBinding:
    def __init__(self, message: str) -> None:
        self.message = message

    async def run(self, model, inputs):
        raise RuntimeError(self.message)


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("AiError: JSON Mode couldn't be met", "invalid_output"),
        ("4006: you have used up your daily free allocation of 10,000 neurons", "quota"),
        ("Network connection lost", "unavailable"),
    ],
)
def test_workers_ai_errors_are_classified(message, kind):
    assert classify_provider_error(message) == kind
    with pytest.raises(AIProviderError) as info:
        asyncio.run(WorkersAIClient(FailingBinding(message)).run("m", {}))
    assert info.value.kind == kind
    assert message not in str(info.value)


def test_rate_limiter_adapter_reads_success_from_dict_or_object():
    class DictBinding:
        async def limit(self, options):
            assert options == {"key": "ip:1"}
            return {"success": False}

    class ObjBinding:
        async def limit(self, options):
            return SimpleNamespace(success=True)

    assert asyncio.run(WorkersRateLimiter(DictBinding()).allow("ip:1")) is False
    assert asyncio.run(WorkersRateLimiter(ObjBinding()).allow("ip:1")) is True


def test_runtime_from_env_reads_vars_and_bindings():
    env = SimpleNamespace(
        ENVIRONMENT="development", ALLOWED_ORIGINS="https://a.github.io/", AI=object()
    )
    runtime = runtime_from_scope({"env": env})
    assert runtime.settings.environment == "development"
    assert "https://a.github.io" in runtime.settings.allowed_origins
    assert runtime.ai is not None and runtime.ip_limiter is None


def test_runtime_without_env_defaults_to_production():
    runtime = runtime_from_scope({})
    assert runtime.settings.is_production
    assert runtime.ai is None


def test_precheck_checks_type_and_declared_length():
    headers = {b"content-type": "application/json", b"content-length": "10"}
    assert body_precheck("POST", "/api/analyze", headers.get, 100) is None
    assert body_precheck("POST", "/api/analyze", headers.get, 5) == "BODY_TOO_LARGE"
    chunked = {b"content-type": "application/json; charset=utf-8"}
    assert body_precheck("POST", "/api/analyze", chunked.get, 5) is None  # enforced while streaming
    bad = {b"content-type": "application/json", b"content-length": "abc"}
    assert body_precheck("POST", "/api/analyze", bad.get, 5) == "INVALID_REQUEST"
    assert body_precheck("POST", "/api/analyze", {b"content-length": "1"}.get, 5) == (
        "UNSUPPORTED_MEDIA_TYPE"
    )
    assert body_precheck("GET", "/api/health", {}.get, 5) is None


def test_read_limited_stops_consuming_stream_after_limit():
    consumed = 0
    closed = False

    async def stream():
        nonlocal consumed, closed
        try:
            for _ in range(100):
                consumed += 1
                yield b"x" * 400
        finally:
            closed = True

    data = asyncio.run(read_limited(stream(), 1000))
    assert len(data) == 1001
    assert consumed == 3
    assert closed is True

    async def small():
        yield b'{"a":'
        yield b"1}"

    assert asyncio.run(read_limited(small(), 1000)) == b'{"a":1}'


def test_streamed_body_beyond_declared_length_is_cut_off():
    """A client that lies about Content-Length is stopped while streaming, before the app runs."""
    settings = load_settings({"MAX_BODY_BYTES": "1024"}.get)
    runtime = Runtime(settings=settings, ai=None, ip_limiter=None, global_limiter=None)
    app_called = False

    async def app(scope, receive, send):
        nonlocal app_called
        app_called = True

    chunks = [b"x" * 600, b"x" * 600, b"x" * 600]
    received = 0

    async def receive():
        nonlocal received
        received += 1
        return {"type": "http.request", "body": chunks[received - 1], "more_body": received < 3}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/analyze",
        "headers": [(b"content-type", b"application/json"), (b"content-length", b"100")],
    }
    asyncio.run(BodyLimitMiddleware(app, lambda _s: runtime)(scope, receive, send))
    assert app_called is False
    assert received == 2  # stopped as soon as the limit was exceeded
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"]["code"] == "BODY_TOO_LARGE"
