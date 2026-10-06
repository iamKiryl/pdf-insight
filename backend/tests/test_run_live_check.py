"""Process exit status of ``evaluation.run_live`` against a fake local HTTP server (no AI)."""

import json
import pathlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from evaluation.checks import EVALUATOR_VERSION, result_digest
from test_evaluation import ADVERSARIAL, REFERENCE, review

BACKEND = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_api():
    """Serves one canned (status, body) per test; records nothing about the request content."""
    state = {"status": 200, "body": b"{}"}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(state["body"])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def run(base_url, out, *extra):
    command = [sys.executable, "-m", "evaluation.run_live", "--case", "synthetic_offer_pl",
               "--label", "t", "--base-url", base_url, "--out", str(out), *extra]  # fmt: skip
    return subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, timeout=60)


def serve(state, status, result):
    state["status"] = status
    state["body"] = json.dumps(result, ensure_ascii=False).encode()


def test_check_exits_zero_only_when_accepted(fake_api, tmp_path):
    state, url = fake_api
    serve(state, 200, REFERENCE)
    review_file = tmp_path / "review.json"
    review_file.write_text(json.dumps(review(REFERENCE)))
    done = run(url, tmp_path, "--check", "--manual-review", str(review_file))
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads((tmp_path / "t" / f"evaluation-{EVALUATOR_VERSION}.json").read_text())
    assert report["status"] == "accepted"
    assert report["manual"]["resultSha256"] == result_digest(REFERENCE)


def test_check_exits_two_when_manual_review_is_pending(fake_api, tmp_path):
    state, url = fake_api
    serve(state, 200, REFERENCE)
    assert run(url, tmp_path, "--check").returncode == 2


def test_check_exits_one_on_semantic_failure(fake_api, tmp_path):
    state, url = fake_api
    serve(state, 200, ADVERSARIAL)
    review_file = tmp_path / "review.json"
    review_file.write_text(json.dumps(review(ADVERSARIAL)))
    assert run(url, tmp_path, "--check", "--manual-review", str(review_file)).returncode == 1


def test_check_exits_one_on_http_error(fake_api, tmp_path):
    state, url = fake_api
    state["status"] = 504
    state["body"] = json.dumps({"error": {"code": "AI_TIMEOUT", "message": "x", "retryable": True}})
    state["body"] = state["body"].encode()
    done = run(url, tmp_path, "--check")
    assert done.returncode == 1
    report = tmp_path / "t" / f"evaluation-{EVALUATOR_VERSION}.json"
    assert json.loads(report.read_text())["status"] == "failed"


def test_check_exits_one_when_server_is_unreachable(tmp_path):
    assert run("http://127.0.0.1:9", tmp_path, "--check").returncode == 1


def test_recording_mode_keeps_exit_zero_even_on_failure(fake_api, tmp_path):
    state, url = fake_api
    serve(state, 200, ADVERSARIAL)
    assert run(url, tmp_path).returncode == 0
    state["status"] = 502
    assert run(url, tmp_path).returncode == 0
