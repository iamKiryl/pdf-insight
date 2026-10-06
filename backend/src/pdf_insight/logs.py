"""Structured operational logs. Only whitelisted, non-content fields can ever be written."""

import json
import sys

ALLOWED_FIELDS = frozenset(
    {
        "event", "outcome", "status", "ms", "attempts", "pageCount", "pagesWithoutText",
        "textChars", "model", "promptVersion", "modelCallsStarted", "modelCallsCompleted",
        "usageReportedCalls", "usageComplete", "reportedPromptTokens", "reportedCompletionTokens",
        "mode", "chunks", "duplicateFacts",
    }
)  # fmt: skip


def log_event(**fields: object) -> None:
    safe = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and isinstance(v, str | int)}
    sys.stdout.write(json.dumps(safe) + "\n")


CALL_FIELDS = frozenset(
    {
        "label",
        "attempt",
        "outcome",
        "ms",
        "promptTokens",
        "completionTokens",
        "finishReason",
        "outputBytes",
    }
)
MAX_PROBLEMS = 10


def log_model_call(problems: list[str] | None = None, **fields: object) -> None:
    """One line per model call (chunked mode). ``problems`` are validation field paths and fixed
    reasons produced by our validators (never quoted source text or model output)."""
    safe: dict[str, object] = {"event": "model_call"}
    safe |= {k: v for k, v in fields.items() if k in CALL_FIELDS and isinstance(v, str | int)}
    if problems:
        safe["problems"] = [str(p)[:160] for p in problems[:MAX_PROBLEMS]]
    sys.stdout.write(json.dumps(safe) + "\n")
