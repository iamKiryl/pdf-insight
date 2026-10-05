"""Review finding P1 (merge identity): distinct obligations/events must never be merged.

Reproduces docs/REVIEW_CHUNKING.md through the real ground_chunk -> merge path.
"""

from pdf_insight.chunking import build_chunks
from pdf_insight.merge import ground_chunk, merge, merge_organizations, parse_chunk_output
from test_merge import OVERVIEW, request_for

TEXT = (
    "Serwis kosztuje 100 PLN netto miesięcznie. Hosting kosztuje 100 PLN netto miesięcznie. "
    "Podpisanie i zapłata: 12.03.2026."
)


def output(amounts=(), dates=()):
    return parse_chunk_output({"amounts": list(amounts), "dates": list(dates),
                               "organizations": [], "people": [], "keywords": []})  # fmt: skip


def amount(context, evidence, page=1, value=100):
    return {
        "value": value, "currency": "PLN", "basis": "net", "period": "monthly",
        "status": "current", "context": context, "page": page, "evidence": evidence,
    }  # fmt: skip


def test_two_obligations_citing_the_same_text_both_survive():
    request = request_for([TEXT])
    chunk = build_chunks(request)[0]
    grounded = ground_chunk(request, chunk, output(
        amounts=[amount("Serwis", TEXT), amount("Hosting", TEXT)],
        dates=[{"date": "2026-03-12", "event": "Podpisanie", "page": 1, "evidence": TEXT},
               {"date": "2026-03-12", "event": "Zapłata", "page": 1, "evidence": TEXT}],
    ))  # fmt: skip
    result, stats = merge(request, OVERVIEW, [grounded])
    assert [a.context for a in result.amounts] == [
        "Serwis (netto, miesięcznie)",
        "Hosting (netto, miesięcznie)",
    ]
    assert [d.context for d in result.dates] == ["Podpisanie", "Zapłata"]
    assert (stats.duplicate_amounts, stats.duplicate_dates) == (0, 0)


def test_equal_snippets_at_different_offsets_of_a_split_page_stay_separate():
    snippet = "Opłata wynosi 200 PLN netto."
    page = snippet + " " + "a" * 10_500 + " " + snippet + " " + "b" * 3_000
    request = request_for([page])
    first, second = build_chunks(request)
    assert snippet in first.segments[0].new_text and snippet in second.segments[0].new_text
    fact = output(amounts=[{**amount("Opłata", snippet, value=200), "period": "unspecified"}])
    result, stats = merge(request, OVERVIEW, [ground_chunk(request, first, fact),
                                              ground_chunk(request, second, fact)])  # fmt: skip
    assert len(result.amounts) == 2  # two occurrences in the source, not one
    assert stats.duplicate_amounts == 0


def test_the_same_event_text_at_different_places_is_not_merged():
    text = "Zawarcie umowy: 12.03.2026. Dalsza treść umowy. Zawarcie umowy: 12.03.2026."
    request = request_for([text])
    chunk = build_chunks(request)[0]
    grounded = ground_chunk(request, chunk, output(dates=[
        {"date": "2026-03-12", "event": "Zawarcie umowy", "page": 1,
         "evidence": "Dalsza treść umowy. Zawarcie umowy: 12.03.2026"},
        {"date": "2026-03-12", "event": "Zawarcie umowy", "page": 1,
         "evidence": "Zawarcie umowy: 12.03.2026. Dalsza"},
    ]))  # fmt: skip
    result, _ = merge(request, OVERVIEW, [grounded])
    assert len(result.dates) == 2


def test_identical_occurrence_and_meaning_still_collapses():
    snippet = "Kwota 5 555,00 zł netto"
    page = "a" * 9_690 + " " + snippet + ". " + "b" * 9_000
    request = request_for([page])
    first, second = build_chunks(request)
    assert snippet in first.segments[0].text and snippet in second.segments[0].overlap
    fact = output(amounts=[{**amount("Kwota", snippet, value=5555), "period": "unspecified"}])
    result, stats = merge(request, OVERVIEW, [ground_chunk(request, first, fact),
                                              ground_chunk(request, second, fact)])  # fmt: skip
    assert len(result.amounts) == 1 and stats.duplicate_amounts == 1


def test_distinct_organizations_sharing_a_prefix_are_kept():
    assert merge_organizations(["Alfa", "Alfa Logistics"]) == ["Alfa", "Alfa Logistics"]
    assert merge_organizations(["Kwadrat Software", "Kwadrat Software S.A."]) == [
        "Kwadrat Software S.A."
    ]
    assert merge_organizations(["Beta", "Beta Holding sp. z o.o."]) == [
        "Beta",
        "Beta Holding sp. z o.o.",
    ]
