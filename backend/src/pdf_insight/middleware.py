"""Pure ASGI middleware: origin allowlist / CORS and a bounded request body.

Both read settings at request time because Worker vars only exist per request (``scope["env"]``).
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

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
    """Only POST /api/analyze accepts a body. ``path`` is the decoded ASGI path (exact match, so
    "/api/analyze/" is not bounded and its body is never read)."""
    return method == "POST" and path in BOUNDED_PATHS


@dataclass(frozen=True)
class BodyPlan:
    """What the Worker entrypoint does with a request body before the ASGI adapter sees it."""

    read_body: bool  # stream the body with a MAX_BODY_BYTES + 1 cap
    keep_declared_length: bool  # forward headers unchanged so the app reports the precheck error


def plan_body(method: str, raw_path: str, headers: Callable[[bytes], str | None], limit: int):
    """Decide per request, from method, path and headers only, whether any body bytes are read.

    The path is percent-decoded exactly like the Workers ASGI adapter does (``unquote`` of the URL
    pathname), so routing here and in FastAPI cannot disagree. Every request that is not
    POST /api/analyze (unknown paths, trailing slash, other methods, preflight) is forwarded without
    its body; the app then answers 404/405/204 and the adapter never buffers the upload.
    """
    path = unquote(raw_path)
    if not is_bounded(method, path):
        return BodyPlan(read_body=False, keep_declared_length=False)
    if body_precheck(method, path, headers, limit) is not None:
        return BodyPlan(read_body=False, keep_declared_length=True)
    return BodyPlan(read_body=True, keep_declared_length=False)


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
    cap = limit + 1
    buffered: list[bytes] = []
    size = 0
    try:
        async for chunk in chunks:
            kept = chunk[: cap - size]  # never retain more than the cap, even from one huge chunk
            buffered.append(kept)
            size += len(kept)
            if size >= cap:
                break
    finally:
        closer = getattr(chunks, "aclose", None)
        if closer is not None:
            await closer()
    return b"".join(buffered)


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


def _without_body() -> Receive:
    """Receive callable for requests whose body must not be read: an empty body, then disconnect.
    It never calls the real ``receive``."""
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    return receive


class BodyLimitMiddleware:
    """Enforces content type, declared length and the actual streamed size before any parsing.

    Bodies of requests other than POST /api/analyze are never read.
    """

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
            await self.app(scope, _without_body(), send)  # same policy as the Worker entrypoint
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
