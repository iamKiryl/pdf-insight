"""Cloudflare Python Worker entrypoint (runs in Pyodide; not imported by unit tests)."""

from js import URL, Headers, Object
from js import Request as JsRequest
from pyodide.ffi import to_js
from workers import WorkerEntrypoint, asgi

from pdf_insight.app import create_app
from pdf_insight.cloudflare import env_var, runtime_from_scope
from pdf_insight.config import load_settings
from pdf_insight.middleware import body_precheck, is_bounded, read_limited

app = create_app(runtime_from_scope)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # The Workers ASGI adapter buffers the whole body before calling the app, so the analyze
        # body is bounded here first: rejected from headers when possible, otherwise read as a
        # stream that is abandoned after MAX_BODY_BYTES + 1 bytes. The app's middleware then
        # produces the standard JSON error (with CORS headers) from what it receives.
        js_request = request.js_object
        method = js_request.method
        if not is_bounded(method, URL.new(js_request.url).pathname):
            return await asgi.fetch(app, js_request, self.env, self.ctx)

        limit = load_settings(lambda name: env_var(self.env, name)).max_body_bytes
        headers = Headers.new(js_request.headers)
        code = body_precheck(method, "/api/analyze", lambda n: _header(headers, n), limit)
        body = b"" if code is not None else await read_limited(_chunks(js_request.body), limit)
        if code is None:
            headers.delete("content-length")  # recomputed for the bounded body
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
