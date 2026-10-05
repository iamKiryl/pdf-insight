"""Pure ASGI middleware: origin allowlist / CORS and a bounded request body.

Both read settings at request time because Worker vars only exist per request (``scope["env"]``).
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from typing import Any

from .errors import ERRORS, error_body
from .runtime import RuntimeFactory

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

BOUNDED_PATHS = frozenset({"/api/analyze"})


def header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


async def send_json(send: Send, status: int, body: dict[str, Any], extra=()) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode()
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(payload)).encode()),
        *extra,
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


async def send_error(send: Send, code: str, extra=()) -> None:
    await send_json(send, ERRORS[code].status, error_body(code), extra)


def is_bounded(method: str, path: str) -> bool:
    return method == "POST" and path in BOUNDED_PATHS


def body_precheck(method: str, path: str, headers: Callable[[bytes], str | None], limit: int):
    """Header-only checks, shared with the Worker entrypoint. Returns an error code or None.

    Content-Length is optional (proxies may stream with chunked encoding); when it is present and
    too large the body is never read. The actual size is always enforced while streaming.
    """
    if not is_bounded(method, path):
        return None
    content_type = (headers(b"content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return "UNSUPPORTED_MEDIA_TYPE"
    length = headers(b"content-length")
    if length is None:
        return None
    try:
        declared = int(length)
    except ValueError:
        return "INVALID_REQUEST"
    if declared < 0:
        return "INVALID_REQUEST"
    if declared > limit:
        return "BODY_TOO_LARGE"
    return None


async def read_limited(chunks: AsyncIterator[bytes], limit: int) -> bytes:
    """Read a body stream but never keep more than ``limit + 1`` bytes.

    Returning ``limit + 1`` bytes signals overflow to the next size check without buffering the
    rest of the stream; the remaining chunks are not read.
    """
    buffered: list[bytes] = []
    size = 0
    try:
        async for chunk in chunks:
            buffered.append(chunk)
            size += len(chunk)
            if size > limit:
                break
    finally:
        closer = getattr(chunks, "aclose", None)
        if closer is not None:
            await closer()
    return b"".join(buffered)[: limit + 1]


class CorsMiddleware:
    """Rejects browser requests from origins outside ALLOWED_ORIGINS and answers preflights.

    CORS only constrains browsers; direct requests without Origin are still rate limited.
    """

    def __init__(self, app: ASGIApp, runtime_factory: RuntimeFactory) -> None:
        self.app = app
        self.runtime_factory = runtime_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = header(scope, b"origin")
        if origin is None:
            await self.app(scope, receive, send)
            return
        settings = self.runtime_factory(scope).settings
        vary = (b"vary", b"Origin")
        if origin.rstrip("/") not in settings.allowed_origins:
            await send_error(send, "ORIGIN_NOT_ALLOWED", [vary])
            return
        cors = [(b"access-control-allow-origin", origin.encode("latin-1")), vary]
        if scope["method"] == "OPTIONS":
            headers = [
                *cors,
                (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"Content-Type"),
                (b"access-control-max-age", b"600"),
            ]
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *cors]
            await send(message)

        await self.app(scope, receive, send_with_cors)


class BodyLimitMiddleware:
    """Enforces content type, declared length and the actual streamed size before any parsing."""

    def __init__(self, app: ASGIApp, runtime_factory: RuntimeFactory) -> None:
        self.app = app
        self.runtime_factory = runtime_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.runtime_factory(scope).settings.max_body_bytes
        code = body_precheck(scope["method"], scope["path"], lambda n: header(scope, n), limit)
        if code is not None:
            await send_error(send, code)
            return
        if not is_bounded(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await send_error(send, "BODY_TOO_LARGE")
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
