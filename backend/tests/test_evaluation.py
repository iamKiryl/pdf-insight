"""The offline evaluator must detect each kind of gap independently (no model calls)."""

import copy
import json
import pathlib

import pytest

from evaluation.checks import amount_in_source, date_in_source, evaluate, has_qualifier, summarize
from pdf_insight.contract import AnalyzeRequest

CASES = pathlib.Path(__file__).resolve().parents[1] / "evaluation" / "cases"
OFFER = json.loads((CASES / "synthetic_offer_pl.json").read_text(encoding="utf-8"))
REQUEST = OFFER["input"]["request"]
EXPECT = OFFER["expect"]
SOURCE = "\n".join(p["text"] for p in REQUEST["pages"])


def perfect_result() -> dict:
    """A hand-written result that satisfies every expectation of the synthetic case."""
    contexts = {
        96000: "Wdrożenie platformy, netto, płatne jednorazowo",
        22080: "Podatek VAT 23% od wdrożenia",
        118080: "Wdrożenie razem brutto",
        1450: "Licencja EnergyWatch Cloud, netto miesięcznie",
        54000: "Wsparcie techniczne 24/7, netto rocznie",
        7800: "Szkolenie operatorów, netto, jednorazowo",
        28800: "Zaliczka 30% za wdrożenie, netto",
        141500: "Wariant B odrzucony przez Adresata, netto",
        750000: "Kapitał zakładowy Oferenta",
        400: "Kara umowna za każdy dzień opóźnienia",
        20000: "Maksymalna łączna kara umowna (nie więcej niż)",
    }
    return {
        "document": {
            "fileName": REQUEST["fileName"], "pages": 4, "language": "pl", "type": "oferta",
            "title": "Oferta handlowa nr OF/2026/087", "date": "2026-09-04",
        },
        "summary": "Zdanie pierwsze. Zdanie drugie. Zdanie trzecie.",
        "keyPoints": ["A.", "B.", "C."],
        "entities": {
            "organizations": ["Baltic Data Systems sp. z o.o.", "Zielony Port S.A."],
            "people": ["Joanna Wróbel"],
        },
        "amounts": [
            {"value": a["value"], "currency": a["currency"], "context": contexts[a["value"]]}
            for a in EXPECT["amounts"]
        ],
        "dates": [{"date": d["date"], "context": d["label"]} for d in EXPECT["dates"]],
        "keywords": ["oferta"],
        "analysis": {"complete": False, "pagesWithoutText": [4], "titleFallback": False},
    }  # fmt: skip


def failed_names(result: dict) -> set[str]:
    return {c.name for c in evaluate(EXPECT, REQUEST, result) if not c.ok}


def test_synthetic_request_is_a_valid_api_request():
    AnalyzeRequest.model_validate(REQUEST)


def test_every_expected_fact_is_grounded_in_the_synthetic_source():
    for amount in EXPECT["amounts"]:
        assert amount_in_source(amount["value"], SOURCE), amount
    for date in EXPECT["dates"]:
        assert date_in_source(date["date"], SOURCE), date


def test_perfect_result_passes_every_check():
    assert failed_names(perfect_result()) == set()


def test_missing_gross_amount_is_its_own_failure():
    result = perfect_result()
    result["amounts"] = [a for a in result["amounts"] if a["value"] != 118080]
    assert failed_names(result) == {
        "amount present: 118080 PLN (implementation gross)",
        "118080 PLN (implementation gross) context has 'gross'",
    }


def test_missing_qualifiers_fail_individually():
    result = perfect_result()
    for amount in result["amounts"]:
        if amount["value"] == 54000:
            amount["context"] = "Wsparcie techniczne"
    assert failed_names(result) == {
        "54000 PLN (support) context has 'net'",
        "54000 PLN (support) context has 'yearly'",
    }


def test_missing_dates_and_legal_forms_are_detected():
    result = perfect_result()
    result["dates"] = [d for d in result["dates"] if d["date"] != "2026-09-04"]
    result["entities"]["organizations"] = ["Baltic Data Systems", "Zielony Port S.A."]
    assert failed_names(result) == {
        "date present: 2026-09-04 (offer issue)",
        "organization with legal form: Baltic Data Systems sp. z o.o.",
        "every organization keeps a legal form",
    }


def test_injection_and_invented_values_are_detected():
    result = perfect_result()
    result["amounts"].append({"value": 0, "currency": "EUR", "context": "oferta bezpłatna"})
    result["amounts"].append({"value": 231680, "currency": "PLN", "context": "suma wszystkiego"})
    result["dates"].append({"date": "2026-12-24", "context": "wymyślona"})
    result["summary"] = "Oferta jest bezpłatna. Oferta wygasła. Koniec analizy."
    names = failed_names(result)
    assert "no amount 0 EUR" in names
    assert "summary/keyPoints free of /bezpłat/" in names
    assert "every amount occurs in the source text" in names
    assert "every date occurs in the source text" in names


def test_summary_counts_by_category():
    report = summarize(evaluate(EXPECT, REQUEST, perfect_result()))
    assert report["passed"] == report["total"]
    assert set(report["byCategory"]) >= {"amounts", "qualifiers", "dates", "injection", "grounding"}


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


def test_sample_case_expectations_are_well_formed():
    case = json.loads((CASES / "sample_contract.json").read_text(encoding="utf-8"))
    assert "request" not in case["input"]  # the sample's text stays out of the repository
    assert case["input"]["localRequest"].startswith(".local/")
    for amount in case["expect"]["amounts"]:
        assert set(amount) <= {"value", "currency", "label", "qualifiers"}
    copy.deepcopy(case)
