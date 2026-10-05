"""Regression tests for raw model-output validation before normalisation (review finding 2).

A missing key must never be treated like an explicit empty value: it triggers the single correction
retry and, if repeated, AI_INVALID_OUTPUT. Explicit null title/date and [] stay valid.
"""

import pytest

from conftest import FakeAI, make_client, make_request, valid_model_output
from pdf_insight.analyzer import ModelOutput
from pdf_insight.prompt import MODEL_OUTPUT_SCHEMA

REQUIRED_KEYS = [
    "insufficientContent", "language", "type", "title", "date", "summary", "keyPoints",
    "organizations", "people", "amounts", "dates", "keywords",
]  # fmt: skip


def without(*keys):
    output = valid_model_output()
    for key in keys:
        del output[key]
    return output


def post(ai):
    return make_client(ai).post(
        "/api/analyze", json=make_request(), headers={"Origin": "https://example.github.io"}
    )


def test_reviewer_reproduction_no_longer_succeeds_silently():
    stripped = without(
        "amounts", "dates", "organizations", "people", "keywords", "date", "title",
        "insufficientContent",
    )  # fmt: skip
    ai = FakeAI(stripped, stripped)
    response = post(ai)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_INVALID_OUTPUT"
    assert len(ai.calls) == 2


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_missing_key_triggers_exactly_one_retry_then_success(key):
    ai = FakeAI(without(key), valid_model_output())
    response = post(ai)
    assert response.status_code == 200
    assert len(ai.calls) == 2
    correction = ai.calls[1]["inputs"]["messages"][-1]["content"]
    assert key in correction


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_missing_key_twice_returns_invalid_output(key):
    ai = FakeAI(without(key), without(key))
    response = post(ai)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_INVALID_OUTPUT"
    assert len(ai.calls) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"amounts": None},
        {"dates": None},
        {"organizations": "Kwadrat Software S.A."},
        {"people": [None]},
        {"keywords": [1, 2]},
        {"keyPoints": None},
        {"amounts": [{"value": 1, "context": "brak waluty"}]},
        {"amounts": [{"value": "184500", "currency": "PLN", "context": "netto"}]},
        {"amounts": [{"value": True, "currency": "PLN", "context": "netto"}]},
        {"dates": [{"date": "2026-03-12"}]},
        {"date": 20260312},
        {"title": 5},
        {"insufficientContent": "false"},
        {"insufficientContent": None},
        {"summary": None},
        {"language": None},
    ],
    ids=lambda o: next(iter(o)) + ":" + type(next(iter(o.values()))).__name__,
)
def test_wrong_raw_shapes_are_retried(overrides):
    ai = FakeAI(valid_model_output(**overrides), valid_model_output())
    assert post(ai).status_code == 200
    assert len(ai.calls) == 2


def test_explicit_null_and_empty_values_are_valid_on_first_attempt():
    output = valid_model_output(
        title=None, date=None, organizations=[], people=[], amounts=[], dates=[], keywords=[]
    )
    ai = FakeAI(output)
    response = post(ai)
    assert response.status_code == 200
    assert len(ai.calls) == 1
    body = response.json()
    assert body["document"]["date"] is None
    assert body["document"]["title"] == "Dokument bez tytułu"
    assert body["analysis"]["titleFallback"] is True
    assert body["amounts"] == [] and body["dates"] == [] and body["keywords"] == []
    assert body["entities"] == {"organizations": [], "people": []}


def test_explicit_insufficient_content_is_honoured_without_other_fields():
    ai = FakeAI({"insufficientContent": True})
    response = post(ai)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_CONTENT"
    assert len(ai.calls) == 1


def test_extra_model_keys_are_ignored_and_metadata_stays_server_owned():
    output = valid_model_output(fileName="evil.pdf", pages=99, analysis={"complete": True})
    response = post(FakeAI(output))
    assert response.status_code == 200
    body = response.json()
    assert body["document"]["fileName"] == "umowa.pdf"
    assert body["document"]["pages"] == 2


def test_requested_json_schema_matches_raw_validator():
    assert set(MODEL_OUTPUT_SCHEMA["required"]) == set(REQUIRED_KEYS)
    assert set(MODEL_OUTPUT_SCHEMA["properties"]) == set(REQUIRED_KEYS)
    assert set(ModelOutput.model_fields) == set(REQUIRED_KEYS)
