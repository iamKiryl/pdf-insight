"""Send one evaluation case to a locally running Worker and evaluate the answer.

    uv run python -m evaluation.run_live --case synthetic_offer_pl --label run-1 \
        --worker-log ../.local/live/worker.log [--manual-review review.json] [--check]

Each invocation is ONE /api/analyze request (the backend may make up to two model calls). Results,
timing, the server's log line and the evaluation are written under the git-ignored .local/
directory; full source payloads never go into the repository. There is no response cache.

Recording mode (default) always exits 0. ``--check`` exits 0 only when the status is
``accepted``, 1 when ``failed`` (including HTTP/connection errors) and 2 when
``needs_manual_review``. A local latency below 30 s never certifies deployed latency.
"""

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

from evaluation.checks import EXIT_CODES, assess

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = pathlib.Path(__file__).resolve().parent / "cases"


def load_case(case_id: str) -> tuple[dict, dict]:
    case = json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))
    source = case["input"]
    if "request" in source:
        return case, source["request"]
    return case, json.loads((ROOT / source["localRequest"]).read_text(encoding="utf-8"))


def log_lines(path: pathlib.Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    text = path.read_text(errors="replace")
    return [line for line in text.splitlines() if line.startswith('{"event"')]


def new_log_line(path: pathlib.Path | None, seen: int) -> dict | None:
    """The dev server writes its log line asynchronously; wait briefly for the new one."""
    if path is None:
        return None
    for _ in range(50):
        lines = log_lines(path)
        if len(lines) > seen:
            return json.loads(lines[-1])
        time.sleep(0.1)
    return None


def parse_result(status: int, payload: bytes) -> dict | None:
    if status != 200:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def post(base_url: str, origin: str, request: dict) -> tuple[int, bytes, int]:
    http = urllib.request.Request(
        f"{base_url}/api/analyze",
        data=json.dumps(request, ensure_ascii=False).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Origin": origin},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(http, timeout=70) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, payload = error.code, error.read()
    except (urllib.error.URLError, TimeoutError) as error:
        status, payload = 0, json.dumps({"connectionError": str(error)}).encode()
    return status, payload, round((time.monotonic() - started) * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--base-url", default="http://localhost:8787")
    parser.add_argument("--origin", default="http://localhost:5173")
    parser.add_argument("--worker-log", type=pathlib.Path)
    parser.add_argument("--manual-review", type=pathlib.Path)
    parser.add_argument("--check", action="store_true", help="exit non-zero unless accepted")
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / ".local" / "live" / "tuning")
    args = parser.parse_args(argv)
    if not args.base_url.startswith(("http://localhost", "http://127.0.0.1")):
        parser.error("--base-url must point at a local dev server")

    case, request = load_case(args.case)
    manual = json.loads(args.manual_review.read_text()) if args.manual_review else None
    out = args.out / args.label
    out.mkdir(parents=True, exist_ok=True)

    seen = len(log_lines(args.worker_log))
    status, payload, elapsed_ms = post(args.base_url, args.origin, request)
    (out / "response.json").write_bytes(payload)
    meta = {"case": args.case, "status": status, "clientMs": elapsed_ms,
            "serverLog": new_log_line(args.worker_log, seen)}  # fmt: skip
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    report = assess(case, request, parse_result(status, payload), http_status=status,
                    latency_ms=elapsed_ms, manual_review=manual)  # fmt: skip
    (out / "evaluation-v3.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    summary = {k: report.get(k) for k in ("status", "reasons", "httpStatus", "latencyMs")}
    if report.get("automatic"):
        summary["automatic"] = {
            k: report["automatic"][k] for k in ("passed", "total", "byCategory")
        }
    print(json.dumps({**meta, "evaluation": summary}, ensure_ascii=False, indent=2))
    for failed in (report.get("automatic") or {}).get("failed", []):
        print(f"FAIL [{failed['category']}] {failed['name']}  <{failed['detail'][:140]}>")
    return EXIT_CODES[report["status"]] if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
