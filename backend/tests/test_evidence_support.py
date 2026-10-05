"""Review finding P1 (evidence support): currency and qualifiers must come from the source
occurrence, never from the model alone. Unsupported facts invalidate the chunk."""

import pytest

from pdf_insight.analyzer import InvalidModelOutput
from pdf_insight.chunking import build_chunks
from pdf_insight.merge import ground_chunk, parse_chunk_output
from test_merge import request_for

PAGE = "Serwis kosztuje 100 PLN netto miesięcznie. Hosting kosztuje 300 PLN netto miesięcznie."


def ground(text, **fields):
    request = request_for([text])
    fact = {"value": 100, "currency": "PLN", "basis": "net", "period": "monthly",
            "status": "current", "context": "Serwis", "page": 1,
            "evidence": "Serwis kosztuje 100"} | fields  # fmt: skip
    output = parse_chunk_output({"amounts": [fact], "dates": [], "organizations": [],
                                 "people": [], "keywords": []})  # fmt: skip
    return ground_chunk(request, build_chunks(request)[0], output)


def test_short_quote_does_not_license_a_contradicting_currency_and_period():
    with pytest.raises(InvalidModelOutput):
        ground(PAGE, currency="USD", period="yearly")


def test_short_quote_does_not_license_a_contradicting_currency():
    with pytest.raises(InvalidModelOutput):
        ground(PAGE, currency="USD")


@pytest.mark.parametrize(
    "fields",
    [{"period": "yearly"}, {"basis": "gross"}, {"status": "rejected"}, {"period": "daily"}],
)
def test_qualifiers_not_stated_at_the_occurrence_are_rejected(fields):
    with pytest.raises(InvalidModelOutput):
        ground(PAGE, **fields)


def test_currency_and_qualifiers_resolved_from_the_source_occurrence():
    grounded = ground(PAGE)  # quote lacks the currency, the source occurrence states it
    assert [(a.currency, a.basis, a.period) for a in grounded.amounts] == [
        ("PLN", "net", "monthly")
    ]


def test_neighbouring_sentence_does_not_support_a_qualifier():
    text = "Serwis kosztuje 100 PLN. Hosting kosztuje 300 PLN netto miesięcznie."
    with pytest.raises(InvalidModelOutput):
        ground(text)  # "netto miesięcznie" belongs to Hosting, not Serwis


def test_amount_without_any_applicable_currency_is_rejected():
    with pytest.raises(InvalidModelOutput):
        ground("Pozycja 3: Serwis kosztuje 100 za całość.", basis="unspecified",
               period="unspecified", evidence="Serwis kosztuje 100")  # fmt: skip


def test_page_level_currency_declaration_supports_table_values():
    text = "FAKTURA\nWaluta: PLN\nZaliczka 30% na wdrożenie | 55 350,00 | 23%"
    evidence = "Zaliczka 30% na wdrożenie | 55 350,00"
    grounded = ground(text, value=55350, basis="unspecified", period="unspecified",
                      context="Zaliczka", evidence=evidence)  # fmt: skip
    assert grounded.amounts[0].currency == "PLN"


def test_stated_status_and_basis_are_accepted():
    text = "Wariant B za 141 500,00 zł netto został odrzucony przez Adresata."
    grounded = ground(text, value=141500, period="unspecified", status="rejected",
                      context="Wariant B", evidence="Wariant B za 141 500,00 zł")  # fmt: skip
    assert grounded.amounts[0].status == "rejected"


def test_unsupported_date_or_missing_quote_is_rejected_not_dropped():
    request = request_for([PAGE + " Termin: 30.06.2026."])
    chunk = build_chunks(request)[0]
    for bad in (
        {"date": "2026-12-24", "event": "Termin", "page": 1, "evidence": "Termin: 30.06.2026"},
        {"date": "2026-06-30", "event": "Termin", "page": 1, "evidence": "nie ma tego 30.06.2026"},
    ):
        output = parse_chunk_output({"amounts": [], "dates": [bad], "organizations": [],
                                     "people": [], "keywords": []})  # fmt: skip
        with pytest.raises(InvalidModelOutput):
            ground_chunk(request, chunk, output)
