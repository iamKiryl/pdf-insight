"""Offline oracle for compact mode: can the code assemble a correct result? (no model calls)

    uv run python -m evaluation.oracle --case sample_contract [--case synthetic_offer_pl]

For every expected amount/date of a case, the oracle selects the candidate whose occurrence lies
inside the fact's cited evidence on the cited page (whitespace-insensitive match), plus the main
date; then it assembles the result with the production code (compact.assemble) and runs the
evaluator's automatic checks. Narrative fields are placeholders: organisation names are given
WITHOUT legal forms, to exercise legal-form resolution; the title is the case's expected fragment.

It proves only that extraction, contexts and assembly can produce a correct result before quota is
spent. It cannot assess the model's actual selection, summary or key points. Exit 0 when every
non-manual automatic check passes, 1 otherwise. The report (with every selected context, for the
separate source review) is written to the git-ignored .local/live/oracle/.
"""

import argparse
import json
import re
import sys

from evaluation.checks import LEGAL_FORMS, evaluate
from evaluation.run_live import ROOT, load_case
from pdf_insight.candidates import Candidate, extract_candidates
from pdf_insight.compact import assemble, parse_selection
from pdf_insight.contract import AnalyzeRequest

OUT = ROOT / ".local" / "live" / "oracle"


def evidence_span(text: str, evidence: str) -> tuple[int, int] | None:
    pattern = r"\s+".join(map(re.escape, evidence.split()))
    match = re.search(pattern, text)
    return (match.start(), match.end()) if match else None


def pick(fact: dict, kind: str, candidates: list[Candidate], texts: dict[int, str]) -> Candidate:
    span = evidence_span(texts[fact["page"]], fact["evidence"])
    if span is None:
        raise LookupError(f"evidence not on page {fact['page']}: {fact['evidence']!r}")
    for c in candidates:
        if c.kind != kind or c.page != fact["page"] or not span[0] <= c.start < span[1]:
            continue
        if kind == "amount" and (float(c.value), c.currency) == (fact["value"], fact["currency"]):
            return c
        if kind == "date" and c.date == fact["date"]:
            return c
    raise LookupError(f"no candidate for {fact['label']} inside its evidence")


def short_name(name: str) -> str:
    for form in LEGAL_FORMS:
        name = re.sub(rf"\s*{form}\s*$", "", name, flags=re.IGNORECASE)
    return name.strip()


def run(case_id: str) -> tuple[bool, dict]:
    case, request = load_case(case_id)
    expect = case["expect"]
    model = AnalyzeRequest.model_validate(request)
    candidates = extract_candidates(model)
    texts = {p.page: p.text for p in model.pages}
    amounts = [pick(f, "amount", candidates, texts) for f in expect.get("amounts", [])]
    dates = [pick(f, "date", candidates, texts) for f in expect.get("dates", [])]
    main = next((c for c in dates if c.date == expect["document"].get("date")), None)
    doc = expect["document"]
    payload = {
        "insufficientContent": False, "language": doc["language"], "type": doc["type"],
        "title": "Dokument " + " ".join(doc.get("titleContains", [])),
        "mainDateId": main.id if main else None,
        "summary": "Zdanie zastępcze pierwsze. Zdanie zastępcze drugie. Zdanie zastępcze trzecie.",
        "keyPoints": ["Punkt zastępczy pierwszy.", "Punkt zastępczy drugi.",
                      "Punkt zastępczy trzeci."],
        "organizations": [short_name(o) for o in expect.get("organizations", [])],
        "people": expect.get("people", []), "keywords": ["oracle"],
        "amountIds": [c.id for c in amounts], "dateIds": [c.id for c in dates],
    }  # fmt: skip
    by_id = {c.id: c for c in candidates}
    result = assemble(model, parse_selection(payload, by_id, model)).model_dump(mode="json")
    checks = evaluate(expect, request, result)
    failed = [c for c in checks if not c.ok and not c.manual]
    report = {
        "case": case_id,
        "note": "oracle selection; narrative fields are placeholders, not model output",
        "candidates": len(candidates),
        "passed": sum(c.ok for c in checks if not c.manual),
        "total": sum(1 for c in checks if not c.manual),
        "failed": [{"name": c.name, "detail": c.detail} for c in failed],
        "manualSubchecks": [{"name": c.name, "detail": c.detail} for c in checks if c.manual],
        "organizations": result["entities"]["organizations"],
        "contexts": {
            "amounts": [
                f"{a['value']} {a['currency']} | {a['context']}" for a in result["amounts"]
            ],
            "dates": [f"{d['date']} | {d['context']}" for d in result["dates"]],
        },
    }
    return not failed, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ok_all = True
    for case_id in args.case:
        ok, report = run(case_id)
        ok_all &= ok
        path = OUT / f"{case_id}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        state = "PASS" if ok else "FAIL"
        print(f"{state} {case_id}: {report['passed']}/{report['total']} automatic checks, "
              f"{len(report['manualSubchecks'])} manual subcheck(s) -> {path}")  # fmt: skip
        for failure in report["failed"]:
            print(f"  FAIL {failure['name']}: {failure['detail']}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
