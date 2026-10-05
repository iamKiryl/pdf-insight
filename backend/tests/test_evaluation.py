"""Evaluator v3 (offline, no model calls): cases, reference answer, adversarial fixture, status."""

import copy
import json
import pathlib

import pytest

from evaluation.checks import (
    MANUAL_DIMENSIONS,
    assess,
    conflicts,
    evaluate,
    has_qualifier,
    result_digest,
    validate_case,
)
from evaluation.sources import amount_in_source, date_in_source
from pdf_insight.contract import AnalyzeRequest

EVAL = pathlib.Path(__file__).resolve().parents[1] / "evaluation"
ROOT = EVAL.parents[1]
OFFER = json.loads((EVAL / "cases" / "synthetic_offer_pl.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((EVAL / "cases" / "sample_contract.json").read_text(encoding="utf-8"))
REQUEST = OFFER["input"]["request"]
EXPECT = OFFER["expect"]
REFERENCE = json.loads((EVAL / "cases" / "synthetic_offer_pl.reference.json").read_text())["result"]
ADVERSARIAL = json.loads((EVAL / "fixtures" / "adversarial_offer_result.json").read_text())[
    "result"
]


def reference() -> dict:
    return copy.deepcopy(REFERENCE)


def failed_names(result: dict) -> set[str]:
    return {c.name for c in evaluate(EXPECT, REQUEST, result) if not c.ok}


def review(result: dict, verdict: str = "pass", **overrides: str) -> dict:
    dims = {d: {"verdict": overrides.get(d, verdict), "note": "test"} for d in MANUAL_DIMENSIONS}
    return {"resultSha256": result_digest(result), "reviewer": "test", "dimensions": dims}


def status(result, *, http_status=200, latency_ms=1000, manual=None) -> str:
    return assess(OFFER, REQUEST, result, http_status=http_status, latency_ms=latency_ms,
                  manual_review=manual)["status"]  # fmt: skip


# ------------------------------------------------------------------ cases


def test_synthetic_request_is_a_valid_api_request():
    AnalyzeRequest.model_validate(REQUEST)


def test_synthetic_case_expectations_cite_exact_evidence():
    assert validate_case(OFFER, REQUEST) == []


def test_case_validation_rejects_wrong_page_snippet_or_value():
    broken = copy.deepcopy(OFFER)
    broken["expect"]["amounts"][0]["page"] = 3
    broken["expect"]["amounts"][1]["evidence"] = "tekst, którego nie ma w dokumencie"
    broken["expect"]["amounts"][2]["value"] = 118081
    broken["expect"]["dates"][0]["page"] = 4  # unreadable page
    assert len(validate_case(broken, REQUEST)) == 4


def test_no_expected_fact_comes_from_an_unreadable_page():
    for case, unreadable in ((OFFER, {4}), (SAMPLE, {11})):
        for kind in ("amounts", "dates"):
            assert all(fact["page"] not in unreadable for fact in case["expect"][kind])


def test_sample_case_text_stays_out_of_the_repository():
    assert "request" not in SAMPLE["input"]
    assert SAMPLE["input"]["localRequest"].startswith(".local/")


def test_sample_case_evidence_matches_local_text_when_available():
    path = ROOT / SAMPLE["input"]["localRequest"]
    if not path.exists():
        pytest.skip("sample text is local-only (.local/ is git-ignored)")
    assert validate_case(SAMPLE, json.loads(path.read_text(encoding="utf-8"))) == []


# ------------------------------------------------------------------ reference and adversarial


def test_reference_answer_passes_every_automatic_check_but_still_needs_review():
    assert failed_names(reference()) == set()
    report = assess(OFFER, REQUEST, reference(), http_status=200, latency_ms=1000)
    assert report["status"] == "needs_manual_review"
    assert set(report["manual"]["dimensions"].values()) == {"unreviewed"}


def test_reference_with_matching_manual_review_is_accepted():
    assert status(reference(), manual=review(reference())) == "accepted"


def test_manual_review_for_a_different_result_is_ignored():
    other = reference()
    other["keywords"] = ["inne"]
    assert status(reference(), manual=review(other)) == "needs_manual_review"


def test_manual_fail_slow_latency_unmeasured_latency_and_http_errors():
    ref = reference()
    assert status(ref, manual=review(ref, summary_factual="fail")) == "failed"
    assert status(ref, latency_ms=30_000, manual=review(ref)) == "failed"
    assert status(ref, latency_ms=None, manual=review(ref)) == "needs_manual_review"
    assert status(None, http_status=504) == "failed"


def test_schema_invalid_result_fails_before_scoring():
    broken = reference()
    broken["keyPoints"] = ["tylko jeden"]
    report = assess(OFFER, REQUEST, broken, http_status=200, latency_ms=1000)
    assert report["status"] == "failed"
    assert report["schemaErrors"]


def test_adversarial_fixture_is_never_accepted():
    adversarial = copy.deepcopy(ADVERSARIAL)
    assert status(adversarial, manual=review(adversarial)) == "failed"
    names = failed_names(adversarial)
    assert "fileName = request fileName" in names
    assert sum("context names the event" in n for n in names) == len(EXPECT["dates"])
    assert sum("no contradicting qualifier" in n for n in names) == len(EXPECT["amounts"])


# ------------------------------------------------------------------ fact-level checks


def test_missing_gross_amount_is_its_own_failure():
    result = reference()
    result["amounts"] = [a for a in result["amounts"] if a["value"] != 118080]
    assert failed_names(result) == {
        "amount present: 118080 PLN (implementation gross, p.2)",
        "118080 PLN (implementation gross, p.2) same entry has 'gross'",
    }


def test_qualifiers_are_judged_on_one_entry_not_pooled_across_duplicates():
    result = reference()
    result["amounts"] = [a for a in result["amounts"] if a["value"] != 54000] + [
        {"value": 54000, "currency": "PLN", "context": "Wsparcie techniczne, netto"},
        {"value": 54000, "currency": "PLN", "context": "Wsparcie techniczne, płatne rocznie"},
    ]
    assert failed_names(result) == {"54000 PLN (support, p.2) same entry has 'yearly'"} or (
        failed_names(result) == {"54000 PLN (support, p.2) same entry has 'net'"}
    )


def test_contradicting_qualifier_fails_even_if_expected_one_is_present():
    result = reference()
    for amount in result["amounts"]:
        if amount["value"] == 96000:
            amount["context"] = "Wdrożenie, netto i brutto, jednorazowo"
    assert failed_names(result) == {
        "96000 PLN (implementation, p.2) entry has no contradicting qualifier"
    }


def test_wrong_currency_is_a_missing_amount_and_ungrounded():
    result = reference()
    for amount in result["amounts"]:
        if amount["value"] == 1450:
            amount["currency"] = "PLN"
    names = failed_names(result)
    assert "amount present: 1450 EUR (cloud licence, p.2)" in names
    assert "every amount occurs in the source with the same currency" in names


def test_injection_markers_and_invented_values_are_detected():
    result = reference()
    result["amounts"].append({"value": 0, "currency": "EUR", "context": "oferta bezpłatna"})
    result["amounts"].append({"value": 231680, "currency": "PLN", "context": "suma wszystkiego"})
    result["dates"].append({"date": "2026-12-24", "context": "wymyślona"})
    result["summary"] = "Oferta jest bezpłatna. Oferta wygasła. Koniec analizy."
    names = failed_names(result)
    assert {"no amount 0 EUR", "summary/keyPoints free of /bezpłat/",
            "every amount occurs in the source with the same currency",
            "every date occurs in the source"} <= names  # fmt: skip


def test_missing_legal_form_and_wrong_coverage_are_detected():
    result = reference()
    result["entities"]["organizations"] = ["Baltic Data Systems", "Zielony Port S.A."]
    result["analysis"] = {"complete": True, "pagesWithoutText": [], "titleFallback": False}
    names = failed_names(result)
    assert "organization with legal form: Baltic Data Systems sp. z o.o." in names
    assert "every organization keeps a legal form" in names
    assert "analysis.pagesWithoutText = request pagesWithoutText" in names


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize(
    ("value", "text", "currency", "found"),
    [
        (123, "Kwota 9123,00 PLN", None, False),  # inside a larger number
        (12.34, "Kwota 12.34 USD", None, True),  # decimal dot
        (184500, "184 500,00 zł netto", "PLN", True),
        (184500, "184 500,00 zł netto", "PLN", True),  # NBSP thousands separator
        (184500, "184.500,00 zł", "PLN", True),
        (184500, "EUR 184,500.00", "EUR", True),
        (184500, "184 500,00 zł netto", "EUR", False),  # changed currency
        (23, "VAT 23% od kwoty", None, False),  # percentage
        (990114, "KRS: 0000990114", None, False),  # identifier
        (12300, "Kwoty: 12 i 300 zł", "PLN", False),  # two adjacent numbers
        (300, "Kwoty: 12 i 300 zł", "PLN", True),
        (12730.5, "wg 1 55 350,00 23% 12 730,50", None, True),
        (55350, "Waluta: PLN\nwg 1 55 350,00 23%", "PLN", True),  # page-level currency
        (2026, "dnia 12.03.2026 r.", None, False),  # part of a date
    ],
)
def test_amount_parsing_counterexamples(value, text, currency, found):
    assert amount_in_source(value, text, currency) is found


@pytest.mark.parametrize(
    ("iso", "text", "found"),
    [
        ("2026-03-12", "w dniu 12.03.2026 r.", True),
        ("2026-04-01", "od 1 kwietnia 2026 r.", True),
        ("2026-03-12", "March 12, 2026", True),
        ("2026-03-12", "112.03.2026", False),
        ("2026-03-12", "2026-03-120", False),
    ],
)
def test_date_parsing(iso, text, found):
    assert date_in_source(iso, text) is found


@pytest.mark.parametrize(
    ("context", "negated"),
    [
        ("zaliczka na wdrożenie", False),  # Polish preposition "na" is not "n/a"
        ("Nie dotyczy", True),
        ("kwota: n/a", True),
    ],
)
def test_negation_markers(context, negated):
    assert ("negation" in conflicts(context, set())) is negated


@pytest.mark.parametrize(
    ("context", "key", "ok"),
    [
        ("abonament netto miesięcznie", "monthly", True),
        ("licencje rocznie", "yearly", True),
        ("internet access fee", "net", False),
        ("Net price per year", "net", True),
        ("wynagrodzenie brutto", "gross", True),
    ],
)
def test_qualifier_vocabulary(context, key, ok):
    assert has_qualifier(context, key) is ok
