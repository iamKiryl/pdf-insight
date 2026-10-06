"""Runtime settings read per request from Worker vars (``env``) or a plain mapping in tests."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

DEFAULT_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

Environment = Literal["production", "development"]
Mode = Literal["single", "chunked", "compact"]


@dataclass(frozen=True)
class Settings:
    environment: Environment
    allowed_origins: frozenset[str]
    max_body_bytes: int
    ai_model: str
    ai_mode: Mode  # code fallback "single"; deployed release config "compact"; "chunked" experiment
    ai_timeout_seconds: float  # ceiling for a single model call
    ai_total_budget_seconds: float  # ceiling for all model calls of one request (incl. retry)
    ai_max_tokens: int

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def _int(raw: str | None, default: int, low: int, high: int) -> int:
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        return default
    return min(max(value, low), high)


def _float(raw: str | None, default: float, low: float, high: float) -> float:
    try:
        value = float(raw) if raw is not None else default
    except ValueError:
        return default
    return min(max(value, low), high)


def _mode(raw: str | None) -> Mode:
    return "chunked" if raw == "chunked" else "compact" if raw == "compact" else "single"


def load_settings(get: Callable[[str], str | None]) -> Settings:
    """Build settings. Anything other than an explicit ``development`` is production (fail safe)."""
    environment: Environment = (
        "development" if get("ENVIRONMENT") == "development" else "production"
    )
    origins = frozenset(
        o.strip().rstrip("/") for o in (get("ALLOWED_ORIGINS") or "").split(",") if o.strip()
    )
    if environment == "development":
        origins = origins | frozenset(DEV_ORIGINS)
    return Settings(
        environment=environment,
        allowed_origins=origins,
        max_body_bytes=_int(get("MAX_BODY_BYTES"), 262_144, 1_024, 1_048_576),
        ai_model=get("AI_MODEL") or DEFAULT_MODEL,
        ai_mode=_mode(get("AI_MODE")),
        ai_timeout_seconds=_float(get("AI_TIMEOUT_SECONDS"), 40.0, 1.0, 60.0),
        ai_total_budget_seconds=_float(get("AI_TOTAL_BUDGET_SECONDS"), 55.0, 1.0, 90.0),
        ai_max_tokens=_int(get("AI_MAX_TOKENS"), 2048, 256, 4096),
    )
