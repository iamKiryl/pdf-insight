"""Chunked analysis (experimental, opt-in with AI_MODE=chunked; see docs/CHUNKING.md).

Schedule: one overview call plus one call per chunk, all started together but limited to
MAX_CONCURRENT_CALLS in flight; the overview is queued first. One overall deadline covers every
call; each call gets min(AI_TIMEOUT_SECONDS, time left). At most ONE corrective retry is allowed
for the whole request (not per chunk), and only for invalid output with enough time left.
Timeouts, quota and provider errors are never retried. If any call fails, all other calls are
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
from .chunking import TooManyChunks, build_chunks
from .config import Settings
from .contract import AnalyzeRequest
from .errors import ApiError
from .merge import OverviewOutput, ground_chunk, merge, parse_chunk_output, parse_overview
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
    dropped_facts: int = 0
    duplicate_facts: int = 0
    retries: int = 0


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
    specs += [
        CallSpec(f"chunk-{c.index}", build_chunk_messages(request, c, len(chunks)),
                 CHUNK_OUTPUT_SCHEMA, settings.ai_max_tokens, parse_chunk_output)
        for c in chunks
    ]  # fmt: skip

    deadline = clock() + settings.ai_total_budget_seconds
    gate = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    retries = _RetryBudget(1)

    async def call(spec: CallSpec) -> Any:
        messages = spec.messages
        while True:
            async with gate:
                remaining = deadline - clock()
                if remaining <= 0:
                    raise ApiError("AI_TIMEOUT")
                inputs = build_inputs(profile, messages, spec.schema, spec.max_tokens)
                usage.start()
                raw_text = ""
                try:
                    raw = await analyzer._wait_for(
                        ai.run(settings.ai_model, inputs),
                        timeout=min(settings.ai_timeout_seconds, remaining),
                    )
                    usage.complete(raw)
                    payload = _parse_payload(raw)
                    raw_text = json.dumps(payload, ensure_ascii=False)
                    return spec.parse(payload)
                except TimeoutError:
                    raise ApiError("AI_TIMEOUT") from None
                except AIProviderError as exc:
                    if exc.kind == "quota":
                        raise ApiError("AI_QUOTA_EXCEEDED") from None
                    if exc.kind != "invalid_output":
                        raise ApiError("AI_UNAVAILABLE") from None
                    problems = ["the model could not produce JSON matching the schema"]
                except InvalidModelOutput as exc:
                    problems = exc.problems
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
    grounded = [ground_chunk(request, chunk, out) for chunk, out in zip(chunks, results[1:],
                                                                         strict=True)]  # fmt: skip
    try:
        result, merge_stats = merge(request, overview, grounded)
    except InvalidModelOutput:
        raise ApiError("AI_INVALID_OUTPUT") from None
    stats.dropped_facts = merge_stats.dropped
    stats.duplicate_facts = merge_stats.duplicate_amounts + merge_stats.duplicate_dates
    return AnalysisOutcome(result, attempts=1 + stats.retries)
