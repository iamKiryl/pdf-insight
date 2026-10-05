"""Shared contract fixtures: the same files are validated by the frontend Zod schema (Vitest)."""

import json

import pytest
from pydantic import ValidationError

from conftest import CONTRACTS, FIXTURES, load_fixture
from pdf_insight.codes import CURRENCIES, LANGUAGES
from pdf_insight.contract import AnalysisResult
from pdf_insight.sentences import count_sentences

ACCEPTED = sorted((FIXTURES / "output" / "accepted").glob("*.json"))
REJECTED = sorted((FIXTURES / "output" / "rejected").glob("*.json"))
SENTENCE_CASES = load_fixture(FIXTURES / "sentences.json")["cases"]


def test_fixture_sets_are_not_empty():
    assert len(ACCEPTED) >= 3
    assert len(REJECTED) >= 20


@pytest.mark.parametrize("path", ACCEPTED, ids=lambda p: p.stem)
def test_accepted_fixtures_validate(path):
    AnalysisResult.model_validate(load_fixture(path)["data"])


@pytest.mark.parametrize("path", REJECTED, ids=lambda p: p.stem)
def test_rejected_fixtures_fail(path):
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(load_fixture(path)["data"])


def test_rejects_non_finite_amount():
    data = load_fixture(ACCEPTED[0])["data"]
    data["amounts"][0]["value"] = float("nan")
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


@pytest.mark.parametrize("case", SENTENCE_CASES, ids=lambda c: c["text"][:40])
def test_sentence_interval_matches_shared_cases(case):
    result = count_sentences(case["text"])
    assert (result.min, result.max, result.valid) == (case["min"], case["max"], case["valid"])


def test_code_lists_mirror_contract():
    codes = json.loads((CONTRACTS / "codes.json").read_text(encoding="utf-8"))
    assert set(codes["languages"]) == LANGUAGES
    assert set(codes["currencies"]) == CURRENCIES
