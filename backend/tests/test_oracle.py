"""The compact oracle (exact expected candidates, production assembly) must pass before live AI."""

import pytest

from evaluation.oracle import run
from evaluation.run_live import load_case


def test_oracle_assembles_a_passing_result_for_the_synthetic_offer():
    ok, report = run("synthetic_offer_pl")
    assert ok, report["failed"]
    assert report["organizations"] == ["Baltic Data Systems sp. z o.o.", "Zielony Port S.A."]
    # the place-and-date header names no role: a manual subcheck, never an automatic pass
    assert [m["name"].split(" ")[0] for m in report["manualSubchecks"]] == ["2026-09-04"]


def test_oracle_assembles_a_passing_result_for_the_sample_when_available():
    try:
        load_case("sample_contract")
    except FileNotFoundError:
        pytest.skip("sample text is local-only (.local/ is git-ignored)")
    ok, report = run("sample_contract")
    assert ok, report["failed"]
    assert report["organizations"] == ["Nordwave Logistics sp. z o.o.", "Kwadrat Software S.A."]
