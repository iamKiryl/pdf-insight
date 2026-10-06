"""Regressions from docs/REVIEW_COMPACT.md (candidates and assembly; mocks, NOT live AI).

Expected values, offsets and excerpts are written out literally here, independently of the
production parser, so a shared parser error cannot hide itself.
"""

import pytest

from pdf_insight.candidates import extract_candidates
from pdf_insight.compact import assemble, parse_selection, resolve_organizations
from pdf_insight.contract import AnalyzeRequest, has_letter
from pdf_insight.numbers import amounts_on_page


def request_for(texts: list[str]) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate({
        "fileName": "d.pdf", "pageCount": len(texts),
        "pages": [{"page": i, "text": t} for i, t in enumerate(texts, start=1)],
        "pagesWithoutText": [i for i, t in enumerate(texts, start=1) if not has_letter(t)],
    })  # fmt: skip


def found(texts, kind="amount"):
    return [c for c in extract_candidates(request_for(texts)) if c.kind == kind]


def money(text):
    return [(str(t.value), t.currency, text[t.start : t.end]) for t in amounts_on_page(1, text)
            if t.adjacent_currency]  # fmt: skip


# ---------------------------------------------------------------- P1: numbers split at a line wrap

WRAP_PROSE = ("Strony ustalają, że łączne wynagrodzenie Wykonawcy za cały okres wynosi 295\n"
              "200,00 zł brutto.")  # fmt: skip


def test_line_wrapped_grouped_amount_is_reconstructed_with_original_offsets():
    assert money(WRAP_PROSE) == [("295200.00", "PLN", "295\n200,00")]
    (candidate,) = found([WRAP_PROSE])
    assert (candidate.start, candidate.end) == (72, 82)
    assert WRAP_PROSE[72:82] == "295\n200,00"
    assert float(candidate.value) == 295200.0 and candidate.currency == "PLN"


def test_line_wrapped_amount_inside_a_long_summary_line():
    text = ("Podsumowanie finansowe (netto): abonament 12 300,00 zł/mies. (295\n"
            "200,00 zł za 24 miesiące) · licencje 8 600 EUR/rok.")  # fmt: skip
    values = [(float(c.value), c.currency) for c in found([text])]
    assert values == [(12300.0, "PLN"), (295200.0, "PLN"), (8600.0, "EUR")]
    assert all(float(c.value) != 200.0 for c in found([text]))  # never the suffix alone


def test_multi_group_wrap_is_reconstructed():
    text = "Łączna kwota do zapłaty za wszystkie etapy prac objętych umową wynosi 1 234\n567,89 zł."
    assert money(text) == [("1234567.89", "PLN", "1 234\n567,89")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # separate table cells/rows: a short row is not a full prose line -> ambiguous, rejected
        ("Pozycja A 12\n300,00 zł", []),
        (
            "Opis pozycji kosztowej oraz jej wartość netto w złotych\nUsługa B ilość 12\n300,00 zł",
            [],
        ),
        # a page number before a wrapped amount: reference label -> ambiguous, rejected
        ("Wersja 1.3 dokumentu, szczegóły znajdują się w załączniku, Strona 4 z 12\n300,00 zł", []),
        # a decimal split after the comma is not reconstructed and never emitted as a prefix
        ("Wynagrodzenie umowne wynosi 184 500,\n00 zł netto.", []),
    ],
)
def test_ambiguous_wraps_are_rejected_not_emitted_as_a_suffix(text, expected):
    assert money(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ilość\n1\n55 350,00 zł", [("55350.00", "PLN", "55 350,00")]),  # 2-digit group: no wrap
        ("KRS 0000990114\n123,00 zł opłaty", [("123.00", "PLN", "123,00")]),  # identifier
        ("Rabat 8%\n120,00 zł za sztukę", [("120.00", "PLN", "120,00")]),  # percentage
        ("Cena 184 500,00 zł netto.", [("184500.00", "PLN", "184 500,00")]),  # one line
    ],
)
def test_separate_values_on_consecutive_lines_stay_separate(text, expected):
    assert money(text) == expected


# ------------------------------------------------------------------ P1: the context keeps its value


def test_long_table_row_context_keeps_the_selected_value_and_currency():
    text = "Opis | " + "x " * 300 + "| 12345 PLN"
    (candidate,) = found([text])
    assert len(candidate.context) <= 500
    assert "»12345 PLN«" in candidate.context
    assert candidate.context.startswith("s. 1: …")  # the cut is visible


def test_long_sentence_context_keeps_the_value_and_its_qualifier():
    text = "Strony ustalają, że " + "warunek " * 80 + "wynagrodzenie wynosi 7 000,00 zł netto."
    (candidate,) = found([text])
    assert len(candidate.context) <= 500
    assert "»7 000,00 zł« netto" in candidate.context


def test_selected_occurrence_is_marked_in_a_multi_value_sentence():
    text = ("Wynagrodzenie wynosi 184 500,00 zł netto, powiększone o podatek VAT 23%, tj. "
            "42 435,00 zł, co daje łącznie 226 935,00 zł brutto.")  # fmt: skip
    contexts = [c.context for c in found([text])]
    assert "»184 500,00 zł« netto" in contexts[0]
    assert "tj. »42 435,00 zł«," in contexts[1]
    assert "»226 935,00 zł« brutto" in contexts[2]
    assert all(c.count("»") == 1 and c.count("«") == 1 for c in contexts)


def test_marker_characters_from_the_source_cannot_fake_a_selection():
    (candidate,) = found(["Cytat »ważne« i opłata 50,00 zł netto."])
    assert candidate.context.count("»") == 1 and "»50,00 zł«" in candidate.context


def test_table_row_marks_the_cell_and_keeps_the_header_separate():
    header = "Etap Zakres Start Koniec Udział Kwota netto"
    page = f"{header}\nE1 Analiza 01.04.2026 30.04.2026 15% 27 675,00 zł\nRazem 100% 184 500,00 zł"
    dates = found([page], "date")
    assert dates[1].context == (
        f"s. 1: [{header}] E1 Analiza 01.04.2026 »30.04.2026« 15% 27 675,00 zł"
    )
    total = found([page])[1]
    assert total.context == f"s. 1: [{header}] Razem 100% »184 500,00 zł«"


def test_flattened_table_rows_below_a_header_are_rows_not_a_garbled_sentence():
    page = ("Kary umowne\nZdarzenie Wysokość kary Limit\n"
            "Opóźnienie Go-live ponad 30 jednorazowo 15 000,00 zł —\ndni\n"
            "Naruszenie poufności 50 000,00 zł za każde naruszenie 200 000,00 zł\n"
            "8. Łączna wysokość kar nie może przekroczyć 20% wynagrodzenia.")  # fmt: skip
    contexts = [c.context for c in found([page])]
    assert contexts == [
        "s. 1: [Zdarzenie Wysokość kary Limit] Opóźnienie Go-live ponad 30 jednorazowo "
        "»15 000,00 zł« —",
        "s. 1: [Zdarzenie Wysokość kary Limit] Naruszenie poufności »50 000,00 zł« za każde "
        "naruszenie 200 000,00 zł",
        "s. 1: [Zdarzenie Wysokość kary Limit] Naruszenie poufności 50 000,00 zł za każde "
        "naruszenie »200 000,00 zł«",
    ]


def test_header_search_stops_at_a_paragraph_and_does_not_swallow_prose():
    page = (
        "Zdarzenie Wysokość kary Limit\n1. Strony ustalają zasady.\n"
        "Zamawiający zapłaci karę 5 000,00 zł za każde naruszenie poufności informacji."
    )
    (candidate,) = found([page])
    assert "[" not in candidate.context and "»5 000,00 zł«" in candidate.context


# ------------------------------------------------------------------ repeated footer metadata

FOOTER = "Wersja 1.3 · 12.03.2026 Strona {n} z 4"


def pages_with_footer():
    bodies = [
        "Umowę zawarto dnia 12.03.2026 r. w Gdańsku.",
        "Termin płatności: 29.03.2026",
        "Odbiór nastąpi 20.04.2026 r.",
        "Gdańsk, 12.03.2026 Gdańsk, 12.03.2026",
    ]
    return [f"{body}\n{FOOTER.format(n=i)}" for i, body in enumerate(bodies, start=1)]


def test_repeated_version_footer_dates_are_not_event_candidates():
    dates = found(pages_with_footer(), "date")
    assert all("Wersja" not in d.context for d in dates)
    assert [(d.page, d.date) for d in dates] == [
        (1, "2026-03-12"), (2, "2026-03-29"), (3, "2026-04-20"), (4, "2026-03-12"),
        (4, "2026-03-12"),
    ]  # fmt: skip


def test_a_dated_event_that_repeats_in_the_body_is_kept():
    pages = [f"Spotkanie odbędzie się 2 kwietnia 2026 r. w siedzibie.\nStrona {i} z 3"
             for i in (1, 2, 3)]  # fmt: skip
    assert [d.date for d in found(pages, "date")] == ["2026-04-02"] * 3


def test_footer_rule_needs_three_pages():
    pages = [f"Treść umowy.\n{FOOTER.format(n=i)}" for i in (1, 2)]
    assert len(found(pages, "date")) == 2  # too few pages to call it a repeated footer


# ------------------------------------------------------------------ dedup and legal forms

BASE = {
    "insufficientContent": False, "language": "pl", "type": "umowa", "title": "Umowa",
    "mainDateId": None,
    "summary": "Umowa została zawarta. Wynagrodzenie jest ustalone. Strony podpisały umowę.",
    "keyPoints": ["Umowa jest zawarta.", "Wynagrodzenie jest netto.", "Strony są dwie."],
    "organizations": [], "people": [], "keywords": ["umowa"], "amountIds": [], "dateIds": [],
}  # fmt: skip


def test_same_fact_same_context_is_deduplicated_but_distinct_obligations_stay():
    page = pages_with_footer()[3] + "\nAbonament 1 000,00 zł miesięcznie. Kaucja 1 000,00 zł."
    request = request_for([*pages_with_footer()[:3], page])
    candidates = [c for c in extract_candidates(request) if c.page == 4]
    by_id = {c.id: c for c in candidates}
    selection = parse_selection(
        BASE | {"dateIds": [c.id for c in candidates if c.kind == "date"],
                "amountIds": [c.id for c in candidates if c.kind == "amount"]},
        by_id,
    )  # fmt: skip
    result = assemble(request, selection)
    assert [d.date for d in result.dates] == ["2026-03-12"]  # same line, same role: one fact
    assert [a.value for a in result.amounts] == [1000.0, 1000.0]  # different obligations


SOURCE = request_for(
    [
        "Nordwave Logistics sp. z o.o. Kwadrat Software S.A.\n"
        "Alfa Beta sp. z o.o. oraz Alfa Beta S.A. są różnymi spółkami.\n"
        "Sprzedawca: Kwadrat Software S.A.",
    ]
)


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (
            ["Nordwave Logistics", "Kwadrat Software"],
            ["Nordwave Logistics sp. z o.o.", "Kwadrat Software S.A."],
        ),
        (["Alfa Beta"], ["Alfa Beta"]),  # two full names in the source: never guess
        (["Gamma"], ["Gamma"]),  # not in the source with a legal form: unchanged
        (["Kwadrat Software", "Kwadrat Software S.A."], ["Kwadrat Software S.A."]),  # duplicate
        (["Software"], ["Software"]),  # a fragment of a name is not resolved
    ],
)
def test_short_organization_names_resolve_only_to_a_unique_full_name(names, expected):
    assert resolve_organizations(names, SOURCE) == expected


# ------------------------------------------------------------------ found reviewing the contexts


def test_currency_marker_after_a_line_break_belongs_to_the_number():
    text = "Wykonawcy przysługuje wynagrodzenie w wysokości 184 500,00\nzł netto (słownie)."
    (candidate,) = found([text])
    assert (float(candidate.value), candidate.currency) == (184500.0, "PLN")
    assert "»184 500,00 zł« netto" in candidate.context


def test_a_line_crossed_by_a_wrapped_number_is_prose_not_a_table_row():
    text = ("Podsumowanie finansowe (netto): wdrożenie 184 500,00 zł · abonament 12 300,00 "
            "zł/mies. (295\n200,00 zł za 24 miesiące) · licencje 8 600 EUR/rok.")  # fmt: skip
    contexts = [c.context for c in found([text])]
    assert all(c.startswith("s. 1: Podsumowanie finansowe (netto):") for c in contexts)
    assert "(»295 200,00 zł« za 24 miesiące)" in contexts[2]
    assert not any(c.startswith("s. 1: 200,00") for c in contexts)


def test_a_sentence_right_below_a_table_is_prose():
    page = ("Lp. Usługa Jednostka Cena netto\n1 Tester roboczogodzina 180,00 zł\n"
            "Ceny nie zawierają VAT. Dojazd rozliczany według stawki 1,15 zł/km oraz\n"
            "kosztów noclegu.")  # fmt: skip
    contexts = [c.context for c in found([page])]
    assert (
        contexts[0] == "s. 1: [Lp. Usługa Jednostka Cena netto] 1 Tester roboczogodzina »180,00 zł«"
    )
    assert contexts[1] == ("s. 1: Dojazd rozliczany według stawki »1,15 zł«/km oraz kosztów "
                           "noclegu.")  # fmt: skip


def test_long_table_keeps_its_header_and_initials_do_not_break_rows():
    rows = "\n".join(
        f"A{i} Zadanie numer {i} P. Kowalski {i:02d}.03.2026 otwarte" for i in range(1, 13)
    )
    page = f"Nr Zadanie Odpowiedzialny Termin Status\n{rows}"
    dates = found([page], "date")
    assert len(dates) == 12
    assert dates[11].context == (
        "s. 1: [Nr Zadanie Odpowiedzialny Termin Status] A12 Zadanie numer 12 P. Kowalski "
        "»12.03.2026« otwarte"
    )


def test_a_plain_line_directly_above_explicit_rows_is_their_header():
    page = ("Etap Wartość netto etapu Rozliczona zaliczka (30%) Do zapłaty netto\n"
            "E1 27 675,00 8 302,50 19 372,50\nWaluta: PLN")  # fmt: skip
    first = found([page])[0]
    assert first.context == ("s. 1: [Etap Wartość netto etapu Rozliczona zaliczka (30%) Do zapłaty "
                             "netto] E1 »27 675,00« 8 302,50 19 372,50")  # fmt: skip


def test_the_next_numbered_paragraph_is_not_part_of_the_sentence():
    page = "1. Umowa obowiązuje od 1 kwietnia 2026 r. (24 miesiące).\n2. Umowa ulega przedłużeniu."
    (date,) = found([page], "date")
    assert date.context.endswith("(24 miesiące).")
