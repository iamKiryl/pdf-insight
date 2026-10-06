"""Person names must be copied from the source (docs/REVIEW_UI_AND_COMPACT_V2.md; mocks, not AI).

Names below are generic test data, not taken from the sample document.
"""

import json
import unicodedata

import pytest

from conftest import ORIGIN, make_client
from pdf_insight.analyzer import InvalidModelOutput
from pdf_insight.candidates import extract_candidates
from pdf_insight.compact import parse_selection, unattested_people
from test_compact import SequenceAI, payload, request_for

SOURCE = (
    "Spółkę reprezentuje Jana Kowalskiego — Członka Zarządu oraz Zofię\n"
    "Nowak.\nPodpisy: Jan Kowalski, Prezes. Zofia Nowak.\n"
    + "Strony ustalają warunki współpracy w zakresie dostaw i serwisu urządzeń. "
    * 4
)
REQUEST = request_for([SOURCE])


@pytest.mark.parametrize(
    "name",
    [
        "Jan Kowalski",  # nominative, attested at the signature
        "Jana Kowalskiego",  # inflected, attested in the introduction: kept as written
        "Zofię Nowak",  # attested across a PDF line break
        "ZOFIA NOWAK",  # case is normalised
        unicodedata.normalize("NFD", "Zofia Nowak"),  # Unicode form is normalised
    ],
)
def test_attested_names_are_accepted(name):
    assert unattested_people([name], REQUEST) == []


@pytest.mark.parametrize(
    "name",
    [
        "Jan Kowalskiego",  # mixed: first name and surname from different occurrences
        "Jana Kowalski",  # mixed the other way
        "Adam Wiśniewski",  # unrelated person
        "Kowal",  # fragment of a word is not a whole-word match
    ],
)
def test_mixed_unrelated_or_partial_names_are_rejected(name):
    assert unattested_people([name], REQUEST) == [name]


def selection_payload(people):
    found = extract_candidates(REQUEST)
    return payload(people=people, amountIds=[], mainDateId=None,
                   dateIds=[c.id for c in found if c.kind == "date"])  # fmt: skip


def test_unattested_name_is_invalid_output_with_its_position_not_its_text():
    by_id = {c.id: c for c in extract_candidates(REQUEST)}
    with pytest.raises(InvalidModelOutput) as info:
        parse_selection(selection_payload(["Jan Kowalski", "Jan Kowalskiego"]), by_id, REQUEST)
    assert len(info.value.problems) == 1
    assert info.value.problems[0].startswith("people.1: not written in the document")
    assert "Kowalskiego" not in info.value.problems[0]  # problems are logged


def test_names_are_not_checked_without_the_request():
    by_id = {c.id: c for c in extract_candidates(REQUEST)}
    parse_selection(selection_payload(["Adam Wiśniewski"]), by_id)  # oracle-style call, no raise


def post(ai):
    request = {"fileName": "d.pdf", "pageCount": 1, "pages": [{"page": 1, "text": SOURCE}],
               "pagesWithoutText": []}  # fmt: skip
    return make_client(ai, env={"AI_MODE": "compact"}).post(
        "/api/analyze", json=request, headers={"Origin": ORIGIN}
    )


def test_mixed_name_triggers_the_single_correction_then_succeeds(capsys):
    ai = SequenceAI(selection_payload(["Jan Kowalskiego"]), selection_payload(["Jan Kowalski"]))
    response = post(ai)
    assert response.status_code == 200
    assert response.json()["entities"]["people"] == ["Jan Kowalski"]
    assert len(ai.calls) == 2
    assert "people.0: not written in the document" in ai.calls[1]["messages"][-1]["content"]
    assert "Kowalskiego" not in capsys.readouterr().out  # no name in the logs


def test_mixed_name_twice_fails_after_two_calls_without_silent_dropping():
    bad = selection_payload(["Jan Kowalskiego"])
    ai = SequenceAI(bad, bad, selection_payload(["Jan Kowalski"]))
    response = post(ai)
    assert response.json()["error"]["code"] == "AI_INVALID_OUTPUT"
    assert len(ai.calls) == 2
    assert json.dumps(response.json()).count("Kowalski") == 0


# ------------------------------------------------------------------ marker leak (live run H)


def test_marker_copied_before_its_value_is_removed_from_text():
    by_id = {c.id: c for c in extract_candidates(REQUEST)}
    body = selection_payload([])
    body["summary"] = ("Umowa jest ważna do dnia ⟦D3⟧31 października 2026 roku. Cena wynosi "
                       "⟦A5⟧ 96 000,00 zł netto. Strony podpisały umowę.")  # fmt: skip
    body["keyPoints"] = ["Kara wynosi ⟦A16⟧400,00 zł.", "Drugi punkt.", "Trzeci punkt."]
    output = parse_selection(body, by_id, REQUEST).output
    assert "⟦" not in output.summary and "31 października" in output.summary
    assert output.keyPoints[0] == "Kara wynosi 400,00 zł."


def test_marker_standing_in_for_a_value_is_invalid_output():
    by_id = {c.id: c for c in extract_candidates(REQUEST)}
    body = selection_payload([])
    body["keyPoints"] = ["Cena wynosi ⟦A5⟧.", "Drugi punkt.", "Trzeci punkt."]
    with pytest.raises(InvalidModelOutput) as info:
        parse_selection(body, by_id, REQUEST)
    assert info.value.problems == ["keyPoints.0: contains an internal marker; write plain text"]
