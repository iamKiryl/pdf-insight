"""Review finding: rejected evidence must not become a clean success. A chunk with unsupported
facts is invalid output inside the single global correction budget (scripted mocks, no live AI)."""

from test_chunked import EMPTY, OVERVIEW, THREE_PAGES, ScriptedAI, amount, make_request, post

UNSUPPORTED = {**EMPTY, "amounts": [amount(999, "kwota 999 zł, której nie ma w tekście", 1)]}


def test_all_facts_rejected_fails_instead_of_an_empty_complete_result():
    ai = ScriptedAI({"overview": OVERVIEW, "chunk-1": [UNSUPPORTED, UNSUPPORTED]})
    response = post(ai, make_request(THREE_PAGES))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_INVALID_OUTPUT"
    assert [label for label, _ in ai.calls].count("chunk-1") == 2  # one correction, then fail


def test_correction_after_rejected_evidence_succeeds():
    texts = [THREE_PAGES[0] + " Opłata wynosi 4 000,00 zł netto.", *THREE_PAGES[1:]]
    good = {**EMPTY, "amounts": [amount(4000, "Opłata wynosi 4 000,00 zł netto", 1, "Opłata")]}
    ai = ScriptedAI({"overview": OVERVIEW, "chunk-1": [UNSUPPORTED, good]})
    response = post(ai, make_request(texts))
    assert response.status_code == 200
    assert [a["value"] for a in response.json()["amounts"]] == [4000.0]
    retry = [m for label, m in ai.calls if label == "chunk-1"][1]
    assert "evidence" in retry[-1]["content"]


def test_rejections_in_two_chunks_exhaust_the_single_global_budget():
    ai = ScriptedAI({"overview": OVERVIEW, "chunk-1": UNSUPPORTED, "chunk-2": UNSUPPORTED})
    response = post(ai, make_request(THREE_PAGES))
    assert response.json()["error"]["code"] == "AI_INVALID_OUTPUT"
    assert len(ai.calls) <= 4 + 1
