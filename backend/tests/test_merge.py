"""Grounding and deterministic merging of chunk outputs (pure functions, no model calls)."""

import pytest

from pdf_insight.analyzer import InvalidModelOutput
from pdf_insight.chunking import build_chunks
from pdf_insight.contract import AnalyzeRequest, has_letter
from pdf_insight.merge import (
    ChunkOutput,
    GroundedAmount,
    ground_chunk,
    labelled_context,
    merge,
    merge_organizations,
    parse_chunk_output,
    parse_overview,
)

PAGE1 = (
    "Umowa nr 5/2026 zawarta w dniu 12.03.2026 r. pomiędzy Alfa Serwis sp. z o.o. a Beta S.A.\n"
    "Wynagrodzenie za wdrożenie wynosi 10 000,00 zł netto. Abonament wynosi 10 000,00 zł netto "
    "miesięcznie. Licencja kosztuje 10 000 EUR rocznie."
)
PAGE2 = (
    "Termin płatności faktury: 12.03.2026. Odbiór końcowy nastąpi 30.06.2026 r.\n"
    "Wariant z dodatkowym modułem za 25 000 zł netto został odrzucony."
)


def request_for(texts: list[str]) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate({
        "fileName": "umowa.pdf",
        "pageCount": len(texts),
        "pages": [{"page": i, "text": t} for i, t in enumerate(texts, start=1)],
        "pagesWithoutText": [i for i, t in enumerate(texts, start=1) if not has_letter(t)],
    })  # fmt: skip


REQUEST = request_for([PAGE1, PAGE2])
CHUNK = build_chunks(REQUEST)[0]


def amount(value, currency, context, evidence, page=1, basis="net", period="unspecified",
           status="current"):  # fmt: skip
    return {"value": value, "currency": currency, "basis": basis, "period": period,
            "status": status, "context": context, "page": page, "evidence": evidence}  # fmt: skip


def date(iso, event, evidence, page=1):
    return {"date": iso, "event": event, "page": page, "evidence": evidence}


def output(amounts=(), dates=(), organizations=(), people=(), keywords=()) -> ChunkOutput:
    return parse_chunk_output({
        "amounts": list(amounts), "dates": list(dates), "organizations": list(organizations),
        "people": list(people), "keywords": list(keywords),
    })  # fmt: skip


OVERVIEW = parse_overview({
    "insufficientContent": False, "language": "pl", "type": "umowa", "title": "Umowa nr 5/2026",
    "date": "2026-03-12",
    "summary": "Umowa dotyczy wdrożenia. Strony to Alfa i Beta. Odbiór nastąpi w czerwcu.",
    "keyPoints": ["Wdrożenie jest płatne.", "Abonament jest miesięczny.", "Licencja jest roczna."],
    "keywords": ["umowa"],
})  # fmt: skip


def test_equal_values_with_different_meaning_currency_or_period_stay_separate():
    grounded = ground_chunk(REQUEST, CHUNK, output(amounts=[
        amount(10000, "PLN", "Wynagrodzenie za wdrożenie", "wdrożenie wynosi 10 000,00 zł netto"),
        amount(10000, "PLN", "Abonament", "Abonament wynosi 10 000,00 zł netto miesięcznie",
               period="monthly"),
        amount(10000, "EUR", "Licencja", "Licencja kosztuje 10 000 EUR rocznie",
               basis="unspecified", period="yearly"),
    ]))  # fmt: skip
    result, stats = merge(REQUEST, OVERVIEW, [grounded])
    assert [(a.value, a.currency) for a in result.amounts] == [
        (10000, "PLN"),
        (10000, "PLN"),
        (10000, "EUR"),
    ]
    assert len(result.amounts) == 3  # three facts, never merged into one total
    assert stats.duplicate_amounts == 0


def test_differently_worded_overlapping_quotes_are_not_assumed_identical():
    """Overlapping quotes alone never establish identity (docs/REVIEW_CHUNKING.md)."""
    first = ground_chunk(REQUEST, CHUNK, output(amounts=[
        amount(10000, "PLN", "Wdrożenie", "Wynagrodzenie za wdrożenie wynosi 10 000,00 zł netto"),
    ]))  # fmt: skip
    again = ground_chunk(REQUEST, CHUNK, output(amounts=[
        amount(10000, "PLN", "Wdrożenie (powtórzone)", "wdrożenie wynosi 10 000,00 zł"),
    ]))  # fmt: skip
    result, stats = merge(REQUEST, OVERVIEW, [first, again])
    assert len(result.amounts) == 2  # ambiguous: kept separate rather than guessed together
    assert stats.duplicate_amounts == 0


def test_different_events_on_the_same_date_stay_separate():
    grounded = ground_chunk(REQUEST, CHUNK, output(dates=[
        date("2026-03-12", "Zawarcie umowy", "zawarta w dniu 12.03.2026 r."),
        date("2026-03-12", "Termin płatności faktury", "Termin płatności faktury: 12.03.2026",
             page=2),
        date("2026-03-12", "Zawarcie umowy", "w dniu 12.03.2026"),  # overlapping, not identical
    ]))  # fmt: skip
    result, stats = merge(REQUEST, OVERVIEW, [grounded])
    assert [d.context for d in result.dates] == [
        "Zawarcie umowy",
        "Zawarcie umowy",
        "Termin płatności faktury",
    ]
    assert stats.duplicate_dates == 0


@pytest.mark.parametrize(
    "bad",
    [
        amount(10000, "PLN", "x", "tekst, którego nie ma w dokumencie 10 000 zł"),  # not in source
        amount(99999, "PLN", "x", "wdrożenie wynosi 10 000,00 zł netto"),  # value not in evidence
        amount(10000, "USD", "x", "wdrożenie wynosi 10 000,00 zł netto"),  # currency contradicts
    ],
)
def test_ungrounded_amounts_make_the_chunk_output_invalid(bad):
    with pytest.raises(InvalidModelOutput):  # never dropped silently (docs/REVIEW_CHUNKING.md)
        ground_chunk(REQUEST, CHUNK, output(amounts=[bad]))


def test_ungrounded_date_makes_the_chunk_output_invalid():
    with pytest.raises(InvalidModelOutput):
        ground_chunk(REQUEST, CHUNK, output(dates=[
            date("2026-12-24", "Wymyślona", "Odbiór końcowy nastąpi 30.06.2026 r.", page=2),
        ]))  # fmt: skip


def test_page_is_taken_from_where_the_evidence_is_found():
    grounded = ground_chunk(REQUEST, CHUNK, output(amounts=[
        amount(25000, "PLN", "Wariant", "modułem za 25 000 zł netto został odrzucony", page=1,
               status="rejected"),
    ]))  # fmt: skip
    assert grounded.amounts[0].page == 2


def test_evidence_matching_tolerates_typographic_quotes_and_spacing():
    text = "Kwota „ryczałt” wynosi 1 500 zł netto – płatna jednorazowo."
    request = request_for([text + " " + "Uzupełnienie treści. " * 20])
    chunk = build_chunks(request)[0]
    grounded = ground_chunk(request, chunk, output(amounts=[
        amount(1500, "PLN", "Ryczałt", 'Kwota "ryczałt" wynosi 1 500 zł netto - płatna'),
    ]))  # fmt: skip
    assert len(grounded.amounts) == 1


def test_structured_qualifiers_are_added_to_context_once_in_document_language():
    base = GroundedAmount(1, "PLN", "net", "monthly", "rejected", "Abonament", 1, 0, 1, 1)
    assert labelled_context(base, "pl") == "Abonament (netto, miesięcznie, odrzucona)"
    stated = GroundedAmount(1, "PLN", "net", "monthly", "current", "Abonament netto miesięcznie",
                            1, 0, 1, 1)  # fmt: skip
    assert labelled_context(stated, "pl") == "Abonament netto miesięcznie"
    assert labelled_context(base, "en") == "Abonament (net, monthly, rejected)"
    assert labelled_context(base, "de") == "Abonament"  # no labels for other languages


def test_organizations_prefer_the_full_legal_name():
    names = ["Alfa Serwis", "Alfa Serwis sp. z o.o.", "beta s.a.", "Beta S.A."]
    assert merge_organizations(names) == ["Alfa Serwis sp. z o.o.", "beta s.a."]


def test_document_fields_come_from_the_overview_and_metadata_from_the_request():
    result, _ = merge(REQUEST, OVERVIEW, [ground_chunk(REQUEST, CHUNK, output())])
    assert result.document.fileName == "umowa.pdf"
    assert result.document.pages == 2
    assert result.document.type == "umowa"
    assert result.analysis.complete is True


@pytest.mark.parametrize(
    "change",
    [
        {"summary": "Za krótko. Tylko dwa zdania."},
        {"keyPoints": ["Jeden.", "Dwa."]},
        {"language": "polski"},
        {"type": "contract"},
        {"date": "12.03.2026"},
    ],
)
def test_invalid_overview_is_invalid_output(change):
    payload = {**OVERVIEW.model_dump(), **change}
    with pytest.raises(InvalidModelOutput):
        parse_overview(payload)


def test_invalid_chunk_output_is_invalid_output():
    with pytest.raises(InvalidModelOutput):
        parse_chunk_output({"amounts": [amount(1, "zł", "x", "1 zł")], "dates": [],
                            "organizations": [], "people": [], "keywords": []})  # fmt: skip
    with pytest.raises(InvalidModelOutput):
        parse_chunk_output({"amounts": [], "dates": []})  # missing keys
