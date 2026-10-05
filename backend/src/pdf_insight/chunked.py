"""Chunked analysis (experimental, opt-in with AI_MODE=chunked; see docs/CHUNKING.md).

Schedule: one overview call plus one call per chunk, all started together but limited to
MAX_CONCURRENT_CALLS in flight; the overview is queued first. One overall deadline covers every
call; each call gets min(AI_TIMEOUT_SECONDS, time left). At most ONE corrective retry is allowed
for the whole request (not per chunk), and only for invalid output with enough time left.
Evidence grounding runs inside each chunk call's validation, so an unsupported fact is invalid
output that uses the same single retry. Timeouts, quota and provider errors are never retried.
If any call fails, all other calls are
cancelled and the request fails: an incomplete extraction is never returned as a result.
Concurrency does not guarantee a latency target.
"""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import analyzer
from .analyzer import (
    MIN_RETRY_SECONDS,
    AnalysisOutcome,
    InvalidModelOutput,
    ModelUsage,
    _parse_payload,
)
from .chunk_prompt import (
    CHUNK_OUTPUT_SCHEMA,
    OVERVIEW_OUTPUT_SCHEMA,
    build_chunk_messages,
    build_overview_messages,
)
from .chunking import Chunk, TooManyChunks, build_chunks
from .config import Settings
from .contract import AnalyzeRequest
from .errors import ApiError
from .logs import log_model_call
from .merge import (
    GroundedChunk,
    OverviewOutput,
    ground_chunk,
    merge,
    parse_chunk_output,
    parse_overview,
)
from .models import build_inputs, profile_for
from .prompt import correction_message
from .runtime import AIClient, AIProviderError

MAX_CONCURRENT_CALLS = 2
OVERVIEW_MAX_TOKENS = 1024


@dataclass(frozen=True)
class CallSpec:
    label: str  # "overview" or "chunk-<n>" (logs/tests only, never content)
    messages: list[dict[str, str]]
    schema: dict[str, Any]
    max_tokens: int
    parse: Callable[[dict[str, Any]], Any]


@dataclass
class ChunkedStats:
    chunks: int = 0
    duplicate_facts: int = 0
    retries: int = 0


def call_details(raw: Any) -> dict[str, Any]:
    """Token usage and finish reason of one response, when the provider reports them."""
    details: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return details
    usage = raw.get("usage")
    if isinstance(usage, dict):
        for source, target in (("prompt_tokens", "promptTokens"),
                               ("completion_tokens", "completionTokens")):  # fmt: skip
            if isinstance(usage.get(source), int) and not isinstance(usage.get(source), bool):
                details[target] = usage[source]
    reason = raw.get("finish_reason")
    choices = raw.get("choices")
    if reason is None and isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reason = choices[0].get("finish_reason")
    if isinstance(reason, str):
        details["finishReason"] = reason[:40]
    return details


class _RetryBudget:
    def __init__(self, allowed: int) -> None:
        self.remaining = allowed

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


async def analyze_chunked(
    request: AnalyzeRequest,
    ai: AIClient,
    settings: Settings,
    usage: ModelUsage | None = None,
    stats: ChunkedStats | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> AnalysisOutcome:
    usage = usage if usage is not None else ModelUsage()
    stats = stats if stats is not None else ChunkedStats()
    profile = profile_for(settings.ai_model)
    if profile is None:
        raise ApiError("SERVICE_MISCONFIGURED")
    try:
        chunks = build_chunks(request)
    except TooManyChunks:
        raise ApiError("DOCUMENT_TOO_LONG") from None
    stats.chunks = len(chunks)

    specs = [CallSpec("overview", build_overview_messages(request), OVERVIEW_OUTPUT_SCHEMA,
                      OVERVIEW_MAX_TOKENS, parse_overview)]  # fmt: skip

    def chunk_parser(chunk: Chunk) -> Callable[[dict[str, Any]], GroundedChunk]:
        # validation + evidence grounding: both inside the retry boundary of this call
        return lambda payload: ground_chunk(request, chunk, parse_chunk_output(payload))

    specs += [
        CallSpec(f"chunk-{c.index}", build_chunk_messages(request, c, len(chunks)),
                 CHUNK_OUTPUT_SCHEMA, settings.ai_max_tokens, chunk_parser(c))
        for c in chunks
    ]  # fmt: skip

    deadline = clock() + settings.ai_total_budget_seconds
    gate = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    retries = _RetryBudget(1)

    async def call(spec: CallSpec) -> Any:
        messages = spec.messages
        attempt = 0
        while True:
            async with gate:
                remaining = deadline - clock()
                if remaining <= 0:
                    raise ApiError("AI_TIMEOUT")
                inputs = build_inputs(profile, messages, spec.schema, spec.max_tokens)
                attempt += 1
                usage.start()
                started = time.monotonic()
                raw_text = ""
                record: dict[str, Any] = {"label": spec.label, "attempt": attempt}

                def done(outcome: str, problems: list[str] | None = None) -> None:
                    ms = round((time.monotonic() - started) * 1000)  # noqa: B023 - this attempt
                    log_model_call(problems, outcome=outcome, ms=ms, **record)  # noqa: B023

                try:
                    raw = await analyzer._wait_for(
                        ai.run(settings.ai_model, inputs),
                        timeout=min(settings.ai_timeout_seconds, remaining),
                    )
                    usage.complete(raw)
                    record |= call_details(raw)
                    payload = _parse_payload(raw)
                    raw_text = json.dumps(payload, ensure_ascii=False)
                    parsed = spec.parse(payload)
                    done("ok")
                    return parsed
                except TimeoutError:
                    done("timeout")
                    raise ApiError("AI_TIMEOUT") from None
                except asyncio.CancelledError:
                    done("cancelled")
                    raise
                except AIProviderError as exc:
                    done(f"provider_{exc.kind}")
                    if exc.kind == "quota":
                        raise ApiError("AI_QUOTA_EXCEEDED") from None
                    if exc.kind != "invalid_output":
                        raise ApiError("AI_UNAVAILABLE") from None
                    problems = ["the model could not produce JSON matching the schema"]
                except InvalidModelOutput as exc:
                    problems = exc.problems
                    done("invalid_output", problems)
            if deadline - clock() < MIN_RETRY_SECONDS:
                raise ApiError("AI_TIMEOUT")
            if not retries.take():
                raise ApiError("AI_INVALID_OUTPUT")
            stats.retries += 1
            history = [{"role": "assistant", "content": raw_text[:8000]}] if raw_text else []
            messages = [*spec.messages, *history, correction_message(problems)]

    tasks = [asyncio.create_task(call(spec)) for spec in specs]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    overview: OverviewOutput = results[0]
    if overview.insufficientContent:
        raise ApiError("INSUFFICIENT_CONTENT")
    grounded: list[GroundedChunk] = list(results[1:])
    try:
        result, merge_stats = merge(request, overview, grounded)
    except InvalidModelOutput:
        raise ApiError("AI_INVALID_OUTPUT") from None
    stats.duplicate_facts = merge_stats.duplicate_amounts + merge_stats.duplicate_dates
    return AnalysisOutcome(result, attempts=1 + stats.retries)
