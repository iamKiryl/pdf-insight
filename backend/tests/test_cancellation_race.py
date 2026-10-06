"""After a terminal failure no queued model call may be dispatched (docs/ADR_COMPACT_ANALYSIS.md).

Observed live: chunk 1 timed out, its semaphore slot was released before the failure cancelled the
other tasks, and chunk 3 was dispatched for 3 ms. Event-controlled fakes (no real waiting).
"""

import asyncio

from pdf_insight.analyzer import ModelUsage
from pdf_insight.chunked import ChunkedStats, analyze_chunked
from pdf_insight.config import load_settings
from pdf_insight.contract import AnalyzeRequest
from pdf_insight.errors import ApiError
from pdf_insight.runtime import AIProviderError
from test_chunked import EMPTY, OVERVIEW, THREE_PAGES, ScriptedAI, make_request

INVALID = {"amounts": "zle"}


class Step:
    def __init__(self, result, wait: asyncio.Event | None = None, signal=None) -> None:
        self.result, self.wait, self.signal = result, wait, signal


class GatedAI:
    """Per label, a list of steps: optionally wait for an event, optionally set one, then answer."""

    def __init__(self, steps: dict[str, list[Step]]) -> None:
        self.steps = steps
        self.dispatched: list[str] = []
        self.events: list[tuple[str, str]] = []  # ("dispatch" | "answer", label) in order

    async def run(self, model, inputs):
        label = ScriptedAI.label(inputs["messages"])
        self.dispatched.append(label)
        self.events.append(("dispatch", label))
        step = self.steps[label].pop(0)
        if step.wait is not None:
            await step.wait.wait()
        if step.signal is not None:
            step.signal.set()
        self.events.append(("answer", label))
        if isinstance(step.result, BaseException):
            raise step.result
        return {"response": step.result}


def run(ai) -> str:
    settings = load_settings({"AI_MODE": "chunked"}.get)
    request = AnalyzeRequest.model_validate(make_request(THREE_PAGES))

    async def main():
        try:
            await analyze_chunked(request, ai, settings, ModelUsage(), ChunkedStats())
        except ApiError as exc:
            return exc.code
        return "ok"

    return asyncio.run(main())


def held() -> asyncio.Event:
    return asyncio.Event()  # never set: the call stays in flight until cancelled


def test_timeout_dispatches_no_queued_call():
    ai = GatedAI({"overview": [Step(OVERVIEW, held())], "chunk-1": [Step(TimeoutError())],
                  "chunk-2": [Step(EMPTY)], "chunk-3": [Step(EMPTY)]})  # fmt: skip
    assert run(ai) == "AI_TIMEOUT"
    assert ai.dispatched == ["overview", "chunk-1"]


def test_non_retryable_provider_error_dispatches_no_queued_call():
    ai = GatedAI({"overview": [Step(OVERVIEW, held())],
                  "chunk-1": [Step(AIProviderError("unavailable"))],
                  "chunk-2": [Step(EMPTY)], "chunk-3": [Step(EMPTY)]})  # fmt: skip
    assert run(ai) == "AI_UNAVAILABLE"
    assert ai.dispatched == ["overview", "chunk-1"]


def test_exhausted_correction_budget_dispatches_no_queued_call():
    first_failed = asyncio.Event()
    ai = GatedAI({
        # overview: invalid at once (uses the single retry), its retry would wait forever
        "overview": [Step(INVALID, signal=first_failed), Step(OVERVIEW, held())],
        # chunk-1: invalid after the overview failed -> budget exhausted -> terminal
        "chunk-1": [Step(INVALID, wait=first_failed)],
        "chunk-2": [Step(EMPTY, held())],  # occupies the freed slot
        "chunk-3": [Step(EMPTY)],
    })  # fmt: skip
    assert run(ai) == "AI_INVALID_OUTPUT"
    # chunk-1's second invalid answer is terminal: nothing may be dispatched after it
    terminal_at = ai.events.index(("answer", "chunk-1"))
    assert [e for e in ai.events[terminal_at:] if e[0] == "dispatch"] == []
    assert "chunk-3" not in ai.dispatched


def test_external_cancellation_dispatches_no_queued_call():
    ai = GatedAI({"overview": [Step(OVERVIEW, held())], "chunk-1": [Step(EMPTY, held())],
                  "chunk-2": [Step(EMPTY)], "chunk-3": [Step(EMPTY)]})  # fmt: skip
    settings = load_settings({"AI_MODE": "chunked"}.get)
    request = AnalyzeRequest.model_validate(make_request(THREE_PAGES))

    async def main():
        task = asyncio.create_task(analyze_chunked(request, ai, settings))
        for _ in range(5):
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        return "finished"

    assert asyncio.run(main()) == "cancelled"
    assert ai.dispatched == ["overview", "chunk-1"]


def test_invalid_output_with_budget_left_is_not_terminal():
    ai = GatedAI({"overview": [Step(OVERVIEW)], "chunk-1": [Step(INVALID), Step(EMPTY)],
                  "chunk-2": [Step(EMPTY)], "chunk-3": [Step(EMPTY)]})  # fmt: skip
    assert run(ai) == "ok"
    assert sorted(ai.dispatched) == ["chunk-1", "chunk-1", "chunk-2", "chunk-3", "overview"]
