"""Model call, validation and exactly one retry on invalid output."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import Settings
from .contract import AnalysisInfo, AnalysisResult, AnalyzeRequest
from .errors import ApiError
from .prompt import MODEL_OUTPUT_SCHEMA, build_messages, correction_message
from .runtime import AIClient, AIProviderError

MAX_ATTEMPTS = 2  # first call + exactly one retry, only for invalid output

FALLBACK_TITLES: dict[str, str] = {
    "pl": "Dokument bez tytułu",
    "en": "Untitled document",
    "de": "Dokument ohne Titel",
    "fr": "Document sans titre",
    "es": "Documento sin título",
    "it": "Documento senza titolo",
    "cs": "Dokument bez názvu",
    "sk": "Dokument bez názvu",
    "uk": "Документ без назви",
    "ru": "Документ без названия",
}
DEFAULT_FALLBACK_TITLE = "Untitled document"


class InvalidModelOutput(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class AnalysisOutcome:
    result: AnalysisResult
    attempts: int


@dataclass
class ModelUsage:
    """Counters for operational logs and quota measurement (never content).

    A call is counted as *started* before it is dispatched, so a timed-out or failed invocation is
    still visible: the provider may have done (and billed) the work even though we stopped waiting.
    *Completed* calls returned a response; token counts are summed only from completed calls whose
    response reported ``usage``. Missing usage is "unknown", never zero consumption.
    """

    started: int = 0
    completed: int = 0
    usage_reported: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def start(self) -> None:
        self.started += 1

    def complete(self, raw: Any) -> None:
        self.completed += 1
        usage = raw.get("usage") if isinstance(raw, dict) else None
        if not isinstance(usage, dict):
            return
        values = [usage.get(key) for key in ("prompt_tokens", "completion_tokens")]
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in values):
            return
        self.usage_reported += 1
        self.prompt_tokens += values[0]
        self.completion_tokens += values[1]

    def log_fields(self) -> dict[str, int | bool]:
        return {
            "modelCallsStarted": self.started,
            "modelCallsCompleted": self.completed,
            "usageReportedCalls": self.usage_reported,
            "usageComplete": self.started == self.usage_reported,
            "reportedPromptTokens": self.prompt_tokens,
            "reportedCompletionTokens": self.completion_tokens,
        }


def fallback_title(language: str) -> str:
    return FALLBACK_TITLES.get(language, DEFAULT_FALLBACK_TITLE)


class _Raw(BaseModel):
    # strict: no str→number or bool→number coercion; extra keys (e.g. a model-invented fileName)
    # are ignored because the server owns metadata.
    model_config = ConfigDict(strict=True, extra="ignore")


class RawAmount(_Raw):
    value: float = Field(allow_inf_nan=False)
    currency: str
    context: str


class RawDate(_Raw):
    date: str
    context: str


class ModelOutput(_Raw):
    """Raw shape requested from the model (prompt.MODEL_OUTPUT_SCHEMA), validated BEFORE any
    normalisation. Every key is required: a missing key is invalid output (one correction retry),
    never an implicit empty value. Only title and date may be explicitly null; lists may be []."""

    insufficientContent: bool
    language: str
    type: str
    title: str | None
    date: str | None
    summary: str
    keyPoints: list[str]
    organizations: list[str]
    people: list[str]
    amounts: list[RawAmount]
    dates: list[RawDate]
    keywords: list[str]


def _clean_list(values: list[str]) -> list[str]:
    """Trim strings and drop blanks and case-insensitive duplicates."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in (value.strip() for value in values):
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            cleaned.append(item)
    return cleaned


def _parse_payload(raw: Any) -> dict[str, Any]:
    """Workers AI returns {"response": <object or JSON string>}; accept both shapes."""
    payload = raw.get("response", raw) if isinstance(raw, dict) else raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            raise InvalidModelOutput(["response is not valid JSON"]) from None
    if not isinstance(payload, dict):
        raise InvalidModelOutput(["response must be a JSON object"])
    return payload


def build_result(payload: dict[str, Any], request: AnalyzeRequest) -> AnalysisResult:
    """Validate the raw model payload, then normalise it into the public contract.

    The server owns fileName/pages/analysis. An explicit ``insufficientContent: true`` is honoured
    even if the model left other fields out, because no result will be built from them.
    """
    if payload.get("insufficientContent") is True:
        raise ApiError("INSUFFICIENT_CONTENT")
    try:
        raw = ModelOutput.model_validate(payload)
    except ValidationError as exc:
        raise InvalidModelOutput(_describe(exc)) from None

    language = raw.language.strip().lower()
    title = (raw.title or "").strip()
    title_fallback = not title
    date = (raw.date or "").strip() or None

    candidate = {
        "document": {
            "fileName": request.fileName.strip(),
            "pages": request.pageCount,
            "language": language,
            "type": raw.type.strip(),
            "title": fallback_title(language) if title_fallback else title,
            "date": date,
        },
        "summary": raw.summary.strip(),
        "keyPoints": _clean_list(raw.keyPoints),
        "entities": {
            "organizations": _clean_list(raw.organizations),
            "people": _clean_list(raw.people),
        },
        "amounts": [
            {"value": a.value, "currency": a.currency.strip().upper(), "context": a.context.strip()}
            for a in raw.amounts
        ],
        "dates": [{"date": d.date.strip(), "context": d.context.strip()} for d in raw.dates],
        "keywords": _clean_list(raw.keywords),
        "analysis": AnalysisInfo(
            complete=not request.pagesWithoutText,
            pagesWithoutText=list(request.pagesWithoutText),
            titleFallback=title_fallback,
        ).model_dump(),
    }
    try:
        return AnalysisResult.model_validate(candidate)
    except ValidationError as exc:
        raise InvalidModelOutput(_describe(exc)) from None


def _describe(exc: ValidationError) -> list[str]:
    """Field paths and messages only — never the offending input values."""
    return [
        f"{'.'.join(str(part) for part in err['loc']) or 'root'}: {err['msg']}"
        for err in exc.errors(include_input=False, include_url=False)
    ]


async def analyze(
    request: AnalyzeRequest,
    ai: AIClient,
    settings: Settings,
    usage: ModelUsage | None = None,
) -> AnalysisOutcome:
    usage = usage if usage is not None else ModelUsage()
    messages: list[dict[str, str]] = build_messages(request)
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        inputs = {
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": MODEL_OUTPUT_SCHEMA},
            "max_tokens": settings.ai_max_tokens,
            "temperature": 0.1,
        }
        raw_text = ""
        try:
            usage.start()
            raw = await asyncio.wait_for(
                ai.run(settings.ai_model, inputs), timeout=settings.ai_timeout_seconds
            )
            usage.complete(raw)
            payload = _parse_payload(raw)
            raw_text = json.dumps(payload, ensure_ascii=False)
            return AnalysisOutcome(build_result(payload, request), attempt)
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
        if attempt < MAX_ATTEMPTS:
            history = [{"role": "assistant", "content": raw_text[:8000]}] if raw_text else []
            messages = [*build_messages(request), *history, correction_message(problems)]
    raise ApiError("AI_INVALID_OUTPUT")
