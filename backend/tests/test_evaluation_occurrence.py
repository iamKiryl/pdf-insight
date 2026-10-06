"""Occurrence-specific qualifier association for source-quote contexts (docs/REVIEW_COMPACT.md).

A compact-mode context quotes the source and marks the selected occurrence as »value«. Several
values in one true sentence (net, VAT, gross) are not a contradiction: qualifiers are associated
with the marked occurrence only. Real contradictions (net/gross swap, wrong period, wrong event,
wrong currency, a marker on a different value) must still fail.
"""

import copy

from evaluation.checks import assess, evaluate, occurrence_segment
from test_evaluation import MANUAL_DIMENSIONS, OFFER, REQUEST, reference, result_digest

SENTENCE = ("s. 4: Wynagrodzenie wynosi {a} netto (słownie: sto złotych 00/100), powiększone o "
            "podatek VAT w stawce 23%, tj. {b}, co daje łącznie {c} brutto.")  # fmt: skip
PLAIN = {"a": "184 500,00 zł", "b": "42 435,00 zł", "c": "226 935,00 zł"}


def marked(which: str) -> str:
    return SENTENCE.format(**{k: f"»{v}«" if k == which else v for k, v in PLAIN.items()})


EXPECT = {
    "amounts": [
        {"value": 184500, "currency": "PLN", "label": "net", "page": 4, "qualifiers": ["net"]},
        {"value": 42435, "currency": "PLN", "label": "vat", "page": 4, "qualifiers": ["vat"]},
        {"value": 226935, "currency": "PLN", "label": "gross", "page": 4,
         "qualifiers": ["gross"]},
    ],
}  # fmt: skip
TEXT = SENTENCE.format(**PLAIN).removeprefix("s. 4: ")
REQ = {"fileName": "d.pdf", "pageCount": 4, "pagesWithoutText": [],
       "pages": [{"page": 4, "text": TEXT}]}  # fmt: skip


def result_with(amounts):
    return {
        "document": {"fileName": "d.pdf", "pages": 4, "language": "pl", "type": "umowa",
                     "title": "U", "date": None},
        "summary": "A. B. C.", "keyPoints": ["a", "b", "c"],
        "entities": {"organizations": [], "people": []},
        "amounts": amounts, "dates": [], "keywords": [],
        "analysis": {"complete": True, "pagesWithoutText": [], "titleFallback": False},
    }  # fmt: skip


def failed(amounts):
    return {c.name for c in evaluate(EXPECT, REQ, result_with(amounts)) if not c.ok}


def entry(value, context):
    return {"value": value, "currency": "PLN", "context": context}


def test_net_vat_and_gross_in_one_true_sentence_are_not_contradictions():
    amounts = [entry(184500, marked("a")), entry(42435, marked("b")), entry(226935, marked("c"))]
    assert failed(amounts) == set()


def test_the_same_unmarked_sentence_still_fails_the_blanket_rule():
    plain = SENTENCE.format(**PLAIN)  # legacy context without a marker: blanket exclusivity
    assert "184500 PLN (net, p.4) entry has no contradicting qualifier" in failed(
        [entry(184500, plain), entry(42435, plain), entry(226935, plain)]
    )


def test_net_gross_swap_fails():
    swapped = "s. 4: Wynagrodzenie wynosi »226 935,00 zł« netto."
    names = failed([entry(184500, marked("a")), entry(42435, marked("b")),
                    entry(226935, swapped)])  # fmt: skip
    assert "226935 PLN (gross, p.4) same entry has 'gross'" in names
    assert "226935 PLN (gross, p.4) entry has no contradicting qualifier" in names


def test_marker_on_a_different_value_fails():
    wrong = marked("b")  # marks 42 435 but the entry claims 184 500
    names = failed([entry(184500, wrong), entry(42435, marked("b")), entry(226935, marked("c"))])
    assert "184500 PLN (net, p.4) entry has no contradicting qualifier" in names


def test_wrong_period_on_the_marked_occurrence_fails():
    expect = {"amounts": [{"value": 12300, "currency": "PLN", "label": "sub", "page": 1,
                           "qualifiers": ["net", "monthly"]}]}  # fmt: skip
    req = {"fileName": "d.pdf", "pageCount": 4, "pagesWithoutText": [],
           "pages": [{"page": 1, "text": "Abonament 12 300,00 PLN netto rocznie."}]}  # fmt: skip
    context = "s. 1: Abonament »12 300,00 PLN« netto rocznie."
    names = {c.name for c in evaluate(expect, req, result_with([entry(12300, context)]))
             if not c.ok}  # fmt: skip
    assert names == {
        "12300 PLN (sub, p.1) same entry has 'monthly'",
        "12300 PLN (sub, p.1) entry has no contradicting qualifier",
    }


def test_table_header_in_brackets_is_not_pooled_into_the_cell():
    context = ("s. 8: [Lp. Nazwa Ilość Wartość netto VAT Kwota VAT Wartość brutto] 1 Zaliczka "
               "30% na wdrożenie wg 1 »55 350,00« 23% 12 730,50 68 080,50")  # fmt: skip
    segment = occurrence_segment(context)
    assert segment is not None and "brutto" not in segment and "Zaliczka" in segment
    assert "12 730,50" not in segment  # the next value cell is a boundary


def test_wrong_event_on_a_marked_date_still_fails():
    result = reference()
    for date in result["dates"]:
        if date["date"] == "2026-10-31":
            date["context"] = "s. 1: Wersja 1.3 · »31.10.2026« Strona 1 z 4"
    names = {c.name for c in evaluate(OFFER["expect"], REQUEST, result) if not c.ok}
    assert any("2026-10-31" in n and "names the event" in n for n in names)


# ------------------------------------------------------------------ issue-date role: manual


def offer_with_manual_issue_date():
    case = copy.deepcopy(OFFER)
    for fact in case["expect"]["dates"]:
        if fact["label"] == "offer issue":
            assert fact.get("eventReview") == "manual"
    return case


def header_date_result():
    result = reference()
    for date in result["dates"]:
        if date["date"] == "2026-09-04":
            date["context"] = "s. 1: Warszawa, dnia »4 września 2026« r."
    return result


def test_unnamed_issue_date_header_is_a_manual_subcheck_not_a_failure():
    result = header_date_result()
    report = assess(offer_with_manual_issue_date(), REQUEST, result, http_status=200,
                    latency_ms=1000)  # fmt: skip
    assert report["status"] == "needs_manual_review"
    assert report["automatic"]["failed"] == []
    assert [m["name"] for m in report["automatic"]["manualSubchecks"]] == [
        "2026-09-04 (offer issue, p.1) context names the event "
        "/sporządz|wystaw|złożen|podpis|data oferty|dzień oferty/ & /ofert/"
    ]
    assert any("manual subcheck" in r for r in report["reasons"])


def test_manual_subcheck_is_resolved_only_by_a_contexts_meaning_review():
    result = header_date_result()
    dims = {d: {"verdict": "pass", "note": "test"} for d in MANUAL_DIMENSIONS}
    review = {"resultSha256": result_digest(result), "reviewer": "t", "dimensions": dims}
    report = assess(offer_with_manual_issue_date(), REQUEST, result, http_status=200,
                    latency_ms=1000, manual_review=review)  # fmt: skip
    assert report["status"] == "accepted"
    dims["contexts_meaning"]["verdict"] = "fail"
    report = assess(offer_with_manual_issue_date(), REQUEST, result, http_status=200,
                    latency_ms=1000, manual_review=review)  # fmt: skip
    assert report["status"] == "failed"


def test_manual_route_does_not_hide_a_missing_date():
    result = reference()
    result["dates"] = [d for d in result["dates"] if d["date"] != "2026-09-04"]
    report = assess(offer_with_manual_issue_date(), REQUEST, result, http_status=200,
                    latency_ms=1000)  # fmt: skip
    assert report["status"] == "failed"
    assert any("date present: 2026-09-04" in f["name"] for f in report["automatic"]["failed"])


def test_person_name_mixed_from_two_inflections_is_ungrounded():
    result = reference()
    result["entities"]["people"] = ["Joanna Wróbla"]  # not written in the offer
    names = {c.name for c in evaluate(OFFER["expect"], REQUEST, result) if not c.ok}
    assert "every person name is written in the source as given" in names
    result["entities"]["people"] = ["Joanna Wróbel"]
    names = {c.name for c in evaluate(OFFER["expect"], REQUEST, result) if not c.ok}
    assert "every person name is written in the source as given" not in names
