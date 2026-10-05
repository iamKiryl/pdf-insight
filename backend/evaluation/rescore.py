"""Re-evaluate SAVED responses offline with the current evaluator (no model or network calls).

    uv run python -m evaluation.rescore ../.local/live/rescore-manifest.json

The manifest lists saved runs: ``[{"label", "case", "response", "httpStatus", "latencyMs",
"manualReview"?}]`` with paths relative to the repository root. Original files are never modified;
each run gets ``<response dir>/evaluation-<evaluatorVersion>.json`` next to its response, and a
summary table is printed.
"""

import json
import pathlib
import sys

from evaluation.checks import EVALUATOR_VERSION, assess
from evaluation.run_live import ROOT, load_case, parse_result


def rescore(entry: dict) -> dict:
    case, request = load_case(entry["case"])
    response_path = ROOT / entry["response"]
    result = parse_result(entry["httpStatus"], response_path.read_bytes())
    manual = None
    if entry.get("manualReview"):
        manual = json.loads((ROOT / entry["manualReview"]).read_text(encoding="utf-8"))
    report = assess(case, request, result, http_status=entry["httpStatus"],
                    latency_ms=entry.get("latencyMs"), manual_review=manual)  # fmt: skip
    target = response_path.parent / f"evaluation-{EVALUATOR_VERSION}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    manifest = json.loads(pathlib.Path(args[0]).read_text(encoding="utf-8"))
    for entry in manifest:
        report = rescore(entry)
        auto = report.get("automatic") or {}
        score = f"{auto['passed']}/{auto['total']}" if auto else "—"
        print(f"{entry['label']:<28} {report['status']:<20} {score:>7}  "
              f"{json.dumps(auto.get('byCategory', {}), ensure_ascii=False)}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
