"""Regression tests for request-body bounding before the Workers ASGI adapter (review finding 1).

``src/worker.py`` imports Pyodide/Workers modules, so it is loaded here with small fakes that record
how much of the incoming body stream is read and what request reaches ``asgi.fetch``.
"""

import asyncio
import importlib
import sys
import types
from urllib.parse import urlsplit

import pytest

from pdf_insight.middleware import plan_body, read_limited

LIMIT = 262_144

# ------------------------------------------------------------ fakes for js / workers / pyodide


class FakeHeaders:
    def __init__(self, source=None):
        items = source.items() if isinstance(source, dict | FakeHeaders) else []
        self._values = {k.lower(): v for k, v in items}

    @classmethod
    def new(cls, source):
        return cls(source)

    def items(self):
        return self._values.items()

    def get(self, name):
        return self._values.get(name.lower())  # stands in for JsNull when missing

    def delete(self, name):
        self._values.pop(name.lower(), None)


class FakeURL:
    @staticmethod
    def new(url):
        return types.SimpleNamespace(pathname=urlsplit(url).path)


class FakeStream:
    """A body stream that can produce far more data than the limit and counts reads."""

    def __init__(self, chunk_size=65_536, chunks=1_000):
        self.chunk_size = chunk_size
        self.remaining = chunks
        self.reads = 0
        self.cancelled = False

    def getReader(self):
        stream = self

        class Reader:
            async def read(self):
                stream.reads += 1
                if stream.remaining == 0:
                    return types.SimpleNamespace(done=True, value=None)
                stream.remaining -= 1
                data = b"x" * stream.chunk_size
                return types.SimpleNamespace(
                    done=False, value=types.SimpleNamespace(to_bytes=lambda: data)
                )

            async def cancel(self):
                stream.cancelled = True

        return Reader()


class FakeJsRequest:
    def __init__(self, url, init):
        self.url = url
        self.method = init["method"]
        self.headers = init["headers"]
        self.body = init.get("body")

    @classmethod
    def new(cls, url, init):
        return cls(url, init)


@pytest.fixture
def worker(monkeypatch):
    calls = []

    js = types.ModuleType("js")
    js.URL = FakeURL
    js.Headers = FakeHeaders
    js.Object = types.SimpleNamespace(fromEntries=dict)
    js.Request = FakeJsRequest

    ffi = types.ModuleType("pyodide.ffi")
    ffi.to_js = lambda value, **_: value
    pyodide = types.ModuleType("pyodide")
    pyodide.ffi = ffi

    workers = types.ModuleType("workers")

    class WorkerEntrypoint:
        def __init__(self, env=None, ctx=None):
            self.env = env
            self.ctx = ctx

    async def fetch(app, request, env, ctx):
        calls.append(request)
        return "response"

    workers.WorkerEntrypoint = WorkerEntrypoint
    workers.asgi = types.SimpleNamespace(fetch=fetch)

    for name, module in {
        "js": js,
        "pyodide": pyodide,
        "pyodide.ffi": ffi,
        "workers": workers,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "worker", raising=False)
    module = importlib.import_module("worker")
    yield module, calls
    sys.modules.pop("worker", None)


def run(worker, method, path, headers=None, stream=None):
    module, calls = worker
    original = FakeJsRequest(
        f"https://api.example{path}",
        {"method": method, "headers": FakeHeaders(headers or {}), "body": stream},
    )
    entry = module.Default(env=types.SimpleNamespace(), ctx=None)
    result = asyncio.run(entry.fetch(types.SimpleNamespace(js_object=original)))
    assert result == "response"
    return calls[-1]


JSON = {"content-type": "application/json"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/analyze/"),  # trailing slash
        ("POST", "/api/unknown"),
        ("POST", "/"),
        ("PUT", "/api/analyze"),
        ("PATCH", "/api/analyze"),
        ("DELETE", "/api/analyze"),
        ("OPTIONS", "/api/analyze"),
        ("GET", "/api/health"),
        ("POST", "//api/analyze"),
    ],
)
def test_non_analyze_requests_never_read_the_body(worker, method, path):
    stream = FakeStream()
    forwarded = run(worker, method, path, {**JSON, "transfer-encoding": "chunked"}, stream)
    assert stream.reads == 0
    assert forwarded.body is None
    assert forwarded.headers.get("content-length") is None
    assert forwarded.headers.get("transfer-encoding") is None


def test_chunked_oversize_analyze_body_is_cut_at_limit_plus_one(worker):
    stream = FakeStream(chunk_size=65_536, chunks=1_000)  # ~65 MB available
    forwarded = run(worker, "POST", "/api/analyze", JSON, stream)
    assert len(forwarded.body) == LIMIT + 1
    assert stream.reads == LIMIT // 65_536 + 1  # stopped right after crossing the limit
    assert stream.cancelled is True


def test_single_huge_chunk_is_sliced_before_retention(worker):
    stream = FakeStream(chunk_size=8 * 1024 * 1024, chunks=3)
    forwarded = run(worker, "POST", "/api/analyze", JSON, stream)
    assert len(forwarded.body) == LIMIT + 1
    assert stream.reads == 1


def test_declared_oversize_is_not_read_and_length_kept_for_413(worker):
    stream = FakeStream()
    forwarded = run(worker, "POST", "/api/analyze", {**JSON, "content-length": "999999"}, stream)
    assert stream.reads == 0
    assert forwarded.body is None
    assert forwarded.headers.get("content-length") == "999999"


def test_percent_encoded_path_is_decoded_like_the_adapter(worker):
    stream = FakeStream(chunk_size=10, chunks=1)
    forwarded = run(worker, "POST", "/api/%61nalyze", JSON, stream)
    assert (
        forwarded.body == b"x" * 10
    )  # same route FastAPI will see, so the body is bounded, not lost


def test_small_analyze_body_is_forwarded_intact(worker):
    stream = FakeStream(chunk_size=100, chunks=2)
    forwarded = run(worker, "POST", "/api/analyze", {**JSON, "content-length": "200"}, stream)
    assert forwarded.body == b"x" * 200
    assert forwarded.headers.get("content-length") is None  # recomputed for the new body


# ------------------------------------------------------------------ pure helpers


def test_plan_body_routes():
    headers = {b"content-type": "application/json"}.get
    assert plan_body("POST", "/api/analyze", headers, LIMIT).read_body is True
    assert plan_body("POST", "/api/analyze/", headers, LIMIT).read_body is False
    assert plan_body("GET", "/api/analyze", headers, LIMIT).read_body is False
    wrong_type = plan_body("POST", "/api/analyze", {}.get, LIMIT)
    assert (wrong_type.read_body, wrong_type.keep_declared_length) == (False, True)


def test_read_limited_retains_at_most_limit_plus_one_bytes_per_chunk():
    seen = []

    async def stream():
        chunk = b"y" * 5_000_000
        seen.append(len(chunk))
        yield chunk
        seen.append("second chunk read")
        yield b"z"

    data = asyncio.run(read_limited(stream(), 1_000))
    assert data == b"y" * 1_001
    assert seen == [5_000_000]
