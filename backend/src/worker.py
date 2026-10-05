"""Cloudflare Python Worker entrypoint (Pyodide; unit-tested with fake js/workers modules)."""

from js import URL, Headers, Object
from js import Request as JsRequest
from pyodide.ffi import to_js
from workers import WorkerEntrypoint, asgi

from pdf_insight.app import create_app
from pdf_insight.cloudflare import env_var, runtime_from_scope
from pdf_insight.config import load_settings
from pdf_insight.middleware import plan_body, read_limited

app = create_app(runtime_from_scope)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # The Workers ASGI adapter queues the whole incoming body before calling the app, so EVERY
        # request is rebuilt here first and the original body stream is never handed to it:
        # - POST /api/analyze: body read as a stream and abandoned after MAX_BODY_BYTES + 1 bytes
        #   (or not read at all when the declared length/content type already fails);
        # - anything else (unknown path, trailing slash, other methods, preflight): no body.
        # The app's middleware then produces the standard JSON error (with CORS headers).
        js_request = request.js_object
        method = js_request.method
        limit = load_settings(lambda name: env_var(self.env, name)).max_body_bytes
        headers = Headers.new(js_request.headers)
        plan = plan_body(
            method, URL.new(js_request.url).pathname, lambda n: _header(headers, n), limit
        )
        body = await read_limited(_chunks(js_request.body), limit) if plan.read_body else b""
        if not plan.keep_declared_length:
            headers.delete("content-length")  # recomputed by the runtime for the new body
            headers.delete("transfer-encoding")
        init = {"method": method, "headers": headers, "body": to_js(body) if body else None}
        bounded = JsRequest.new(js_request.url, to_js(init, dict_converter=Object.fromEntries))
        return await asgi.fetch(app, bounded, self.env, self.ctx)


def _header(headers, name: bytes) -> str | None:
    value = headers.get(name.decode())
    return value if isinstance(value, str) else None  # missing headers are JsNull


async def _chunks(stream):
    if not stream:
        return
    reader = stream.getReader()
    try:
        while True:
            result = await reader.read()
            if result.done:
                return
            yield result.value.to_bytes()
    finally:
        await reader.cancel()
