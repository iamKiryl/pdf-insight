"""Structured operational logs. Only whitelisted, non-content fields can ever be written."""

import json
import sys

ALLOWED_FIELDS = frozenset(
    {
        "event", "outcome", "status", "ms", "attempts", "pageCount", "pagesWithoutText",
        "textChars", "modelCalls", "promptTokens", "completionTokens",
    }
)  # fmt: skip


def log_event(**fields: object) -> None:
    safe = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and isinstance(v, str | int)}
    sys.stdout.write(json.dumps(safe) + "\n")
