"""Send one evaluation case to a locally running Worker and evaluate the answer.

    uv run python -m evaluation.run_live --case synthetic_offer_pl --label gemma-1 \
        --worker-log ../.local/live/worker.log

Each invocation is ONE /api/analyze request (the backend may make up to two model calls). Results,
timing and the server's log line are written under the git-ignored .local/ directory; full source
payloads never go into the repository. There is no response cache.
"""

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request

from evaluation.checks import evaluate, summarize

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = pathlib.Path(__file__).resolve().parent / "cases"


def load_case(case_id: str) -> tuple[dict, dict]:
    case = json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))
    source = case["input"]
    if "request" in source:
        return case, source["request"]
    return case, json.loads((ROOT / source["localRequest"]).read_text(encoding="utf-8"))


def last_log_line(path: pathlib.Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    lines = [
        ln for ln in path.read_text(errors="replace").splitlines() if ln.startswith('{"event"')
    ]
    return json.loads(lines[-1]) if lines else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--base-url", default="http://localhost:8787")
    parser.add_argument("--origin", default="http://localhost:5173")
    parser.add_argument("--worker-log", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / ".local" / "live" / "tuning")
    args = parser.parse_args()

    if not args.base_url.startswith(("http://localhost", "http://127.0.0.1")):
        parser.error("--base-url must point at a local dev server")
    case, request = load_case(args.case)
    out = args.out / args.label
    out.mkdir(parents=True, exist_ok=True)
    body = json.dumps(request, ensure_ascii=False).encode()
    http = urllib.request.Request(
        f"{args.base_url}/api/analyze",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": args.origin},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(http, timeout=70) as response:
            status, payload = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, payload = error.code, error.read()
    elapsed_ms = round((time.monotonic() - started) * 1000)

    (out / "response.json").write_bytes(payload)
    log = last_log_line(args.worker_log)
    meta = {"case": args.case, "status": status, "clientMs": elapsed_ms, "serverLog": log}
    report = None
    if status == 200:
        result = json.loads(payload)
        report = summarize(evaluate(case["expect"], request, result))
        (out / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps({**meta, "evaluation": report and {k: report[k] for k in
                                                         ("passed", "total", "byCategory")}},
                     ensure_ascii=False, indent=2))  # fmt: skip
    if report:
        for failed in report["failed"]:
            print(f"FAIL [{failed['category']}] {failed['name']}  <{failed['detail'][:140]}>")


if __name__ == "__main__":
    main()
