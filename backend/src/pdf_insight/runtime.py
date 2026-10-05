"""Per-request runtime: settings plus Cloudflare bindings behind small protocols.

The FastAPI app only depends on these protocols, so tests inject fakes and the Workers-specific
adapters stay in ``cloudflare.py``.
"""

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Settings


class AIProviderError(Exception):
    """Raised by AI clients. ``kind`` is one of: invalid_output, quota, unavailable."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class AIClient(Protocol):
    async def run(self, model: str, inputs: dict[str, Any]) -> Any: ...


class RateLimiter(Protocol):
    async def allow(self, key: str) -> bool: ...


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    ai: AIClient | None
    ip_limiter: RateLimiter | None
    global_limiter: RateLimiter | None


RuntimeFactory = Callable[[MutableMapping[str, Any]], Runtime]


def classify_provider_error(message: str) -> str:
    """Map provider error text to a category without exposing the text to clients or logs."""
    text = message.lower()
    if "json mode couldn't be met" in text or "json mode could not be met" in text:
        return "invalid_output"
    if any(marker in text for marker in ("4006", "neuron", "quota", "daily free allocation")):
        return "quota"
    return "unavailable"
