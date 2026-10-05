"""Regressions from docs/REVIEW_EVALUATION.md.

All six cases failed against the evaluator before the fix (output kept in
.local/live/eval-regressions-before-fix.txt). They now assert the corrected behaviour.
"""

from evaluation.checks import assess
from evaluation.sources import amount_in_source
from test_evaluation import OFFER, REQUEST, failed_names, reference


def test_amount_is_not_found_inside_a_larger_number():
    assert amount_in_source(123, "Kwota 9123,00 PLN") is False


def test_decimal_dot_amount_is_found():
    assert amount_in_source(12.34, "Kwota 12.34 USD") is True


def test_wrong_date_contexts_fail():
    result = reference()
    for date in result["dates"]:
        date["context"] = "Nieprawdziwa data rozpoczęcia zatrudnienia"
    assert sum("context names the event" in name for name in failed_names(result)) == 6


def test_keyword_soup_amount_contexts_fail():
    soup = "Nie dotyczy: netto brutto VAT miesięcznie rocznie jednorazowo odrzucony budżet kapitał "
    soup += "zaliczka maksymalna kara za dzień"
    result = reference()
    for amount in result["amounts"]:
        amount["context"] = soup
    assert sum("no contradicting qualifier" in name for name in failed_names(result)) == 11


def test_wrong_file_name_fails():
    result = reference()
    result["document"]["fileName"] = "other.pdf"
    assert failed_names(result) == {"fileName = request fileName"}


def test_nonsense_summary_is_not_counted_as_passed():
    result = reference()
    result["summary"] = (
        "Dokument nakazuje zapłatę miliona euro. Wszystkie zobowiązania anulowano. "
        "Umowa jest tajna."
    )
    report = assess(OFFER, REQUEST, result, http_status=200, latency_ms=1000)
    # Offline checks cannot judge the summary's meaning: it must stay unreviewed, never "passed".
    assert report["status"] == "needs_manual_review"
    assert report["manual"]["dimensions"]["summary_factual"] == "unreviewed"
