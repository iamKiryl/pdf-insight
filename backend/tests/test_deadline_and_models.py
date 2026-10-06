"""Overall AI deadline (controlled clock, no real sleeping) and per-model request styles."""

import asyncio
import json

import pytest

from conftest import ORIGIN, FakeAI, make_client, make_request, valid_model_output
from pdf_insight import analyzer
from pdf_insight.analyzer import ModelUsage, analyze
from pdf_insight.config import load_settings
from pdf_insight.contract import AnalyzeRequest
from pdf_insight.errors import ApiError
from pdf_insight.models import MODEL_PROFILES, build_inputs, output_content, profile_for
from pdf_insight.runtime import AIProviderError

GEMMA = "@cf/google/gemma-4-26b-a4b-it"
LLAMA = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TimedAI:
    """Each call 'takes' the given number of seconds on the fake clock, then returns/raises."""

    def __init__(self, clock: Clock, *steps: tuple[float, object]) -> None:
        self.clock = clock
        self.steps = list(steps)
        self.calls = 0

    async def run(self, model, inputs):
        self.calls += 1
        seconds, result = self.steps.pop(0)
        self.clock.now += seconds
        if isinstance(result, BaseException):
            raise result
        return {"response": result}


@pytest.fixture
def timeouts(monkeypatch):
    seen: list[float] = []

    async def recording_wait_for(coro, timeout):
        seen.append(timeout)
        return await coro

    monkeypatch.setattr(analyzer, "_wait_for", recording_wait_for)
    return seen


def run_analyze(ai, clock, env=None):
    settings = load_settings({"AI_MODEL": LLAMA, **(env or {})}.get)
    request = AnalyzeRequest.model_validate(make_request())
    usage = ModelUsage()
    try:
        return asyncio.run(analyze(request, ai, settings, usage, clock=clock)), usage
    except ApiError as exc:
        return exc.code, usage


def test_defaults_are_failure_ceilings_from_the_contract():
    settings = load_settings(lambda _: None)
    assert settings.ai_timeout_seconds == 40
    assert settings.ai_total_budget_seconds == 55


def test_retry_uses_remaining_overall_budget(timeouts):
    clock = Clock()
    ai = TimedAI(clock, (30, valid_model_output(keyPoints=["x"])), (20, valid_model_output()))
    outcome, usage = run_analyze(ai, clock)
    assert outcome.attempts == 2
    assert timeouts == [40, 25]  # second call limited by the 25 s left of 55 s
    assert (usage.started, usage.completed) == (2, 2)


def test_no_retry_when_too_little_budget_remains(timeouts):
    clock = Clock()
    ai = TimedAI(clock, (51, valid_model_output(keyPoints=["x"])), (1, valid_model_output()))
    code, usage = run_analyze(ai, clock)
    assert code == "AI_TIMEOUT"
    assert ai.calls == 1
    assert timeouts == [40]
    assert usage.started == 1


def test_first_call_is_capped_by_total_budget_when_smaller(timeouts):
    clock = Clock()
    ai = TimedAI(clock, (1, valid_model_output()))
    run_analyze(ai, clock, {"AI_TOTAL_BUDGET_SECONDS": "30", "AI_TIMEOUT_SECONDS": "40"})
    assert timeouts == [30]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "AI_TIMEOUT"),
        (AIProviderError("quota"), "AI_QUOTA_EXCEEDED"),
        (AIProviderError("unavailable"), "AI_UNAVAILABLE"),
    ],
)
def test_timeouts_and_provider_failures_are_never_retried(timeouts, error, code):
    clock = Clock()
    ai = TimedAI(clock, (5, error), (1, valid_model_output()))
    result, usage = run_analyze(ai, clock)
    assert result == code
    assert ai.calls == 1
    assert (usage.started, usage.completed) == (1, 0)


def test_unknown_model_fails_closed_without_calling_provider():
    ai = FakeAI(valid_model_output())
    client = make_client(ai, env={"AI_MODEL": "@cf/some/unlisted-model"})
    response = client.post("/api/analyze", json=make_request(), headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_MISCONFIGURED"
    assert ai.calls == []


# ------------------------------------------------------------------ request/response styles


def test_workers_style_inputs_for_llama():
    inputs = build_inputs(profile_for(LLAMA), [{"role": "user", "content": "x"}], {"a": 1}, 2048)
    assert inputs["response_format"] == {"type": "json_schema", "json_schema": {"a": 1}}
    assert "chat_template_kwargs" not in inputs


def test_openai_style_inputs_for_gemma_disable_reasoning():
    inputs = build_inputs(profile_for(GEMMA), [{"role": "user", "content": "x"}], {"a": 1}, 2048)
    assert inputs["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "document_analysis", "schema": {"a": 1}, "strict": True},
    }
    assert inputs["chat_template_kwargs"] == {"enable_thinking": False}


def test_output_content_reads_both_styles():
    assert output_content({"response": {"a": 1}}) == {"a": 1}
    assert output_content({"choices": [{"message": {"content": '{"a": 1}'}}]}) == '{"a": 1}'
    assert output_content({"choices": []}) == {"choices": []}


class ChoicesAI(FakeAI):
    """OpenAI chat-completions style responses (Gemma 4 on Workers AI)."""

    async def run(self, model, inputs):
        result = await super().run(model, inputs)
        content = json.dumps(result["response"], ensure_ascii=False)
        return {
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }


def test_full_analysis_with_openai_style_model(capsys):
    ai = ChoicesAI(valid_model_output())
    client = make_client(ai, env={"AI_MODEL": GEMMA})
    response = client.post("/api/analyze", json=make_request(), headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert ai.calls[0]["model"] == GEMMA
    assert ai.calls[0]["inputs"]["response_format"]["json_schema"]["name"] == "document_analysis"
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (line["model"], line["usageComplete"], line["reportedPromptTokens"]) == (
        GEMMA,
        True,
        100,
    )


def test_every_profiled_model_has_a_known_style():
    assert {p.style for p in MODEL_PROFILES.values()} <= {"workers", "openai"}
