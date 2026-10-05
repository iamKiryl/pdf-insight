"""Model call, validation and exactly one retry on invalid output."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

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


def fallback_title(language: str) -> str:
    return FALLBACK_TITLES.get(language, DEFAULT_FALLBACK_TITLE)


def _clean_str(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _clean_list(values: Any) -> Any:
    """Trim strings and drop blanks and case-insensitive duplicates; validation handles the rest."""
    if not isinstance(values, list):
        return values
    seen: set[str] = set()
    cleaned: list[Any] = []
    for item in values:
        item = _clean_str(item)
        if isinstance(item, str):
            if not item or item.casefold() in seen:
                continue
            seen.add(item.casefold())
        cleaned.append(item)
    return cleaned


def _clean_objects(values: Any, fields: tuple[str, ...]) -> Any:
    if not isinstance(values, list):
        return values
    cleaned = []
    for item in values:
        if isinstance(item, dict):
            item = {k: _clean_str(v) for k, v in item.items() if k in fields}
            if "currency" in item and isinstance(item["currency"], str):
                item["currency"] = item["currency"].upper()
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
    """Normalise model output into the public contract; server owns fileName/pages/analysis."""
    if payload.get("insufficientContent") is True:
        raise ApiError("INSUFFICIENT_CONTENT")

    language = _clean_str(payload.get("language"))
    language = language.lower() if isinstance(language, str) else language
    title = _clean_str(payload.get("title"))
    title_fallback = title is None or title == ""
    if title_fallback:
        title = fallback_title(language if isinstance(language, str) else "")
    date = _clean_str(payload.get("date"))

    candidate = {
        "document": {
            "fileName": request.fileName.strip(),
            "pages": request.pageCount,
            "language": language,
            "type": _clean_str(payload.get("type")),
            "title": title,
            "date": None if date == "" else date,
        },
        "summary": _clean_str(payload.get("summary")),
        "keyPoints": _clean_list(payload.get("keyPoints")),
        "entities": {
            "organizations": _clean_list(payload.get("organizations", [])),
            "people": _clean_list(payload.get("people", [])),
        },
        "amounts": _clean_objects(payload.get("amounts", []), ("value", "currency", "context")),
        "dates": _clean_objects(payload.get("dates", []), ("date", "context")),
        "keywords": _clean_list(payload.get("keywords", [])),
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


async def analyze(request: AnalyzeRequest, ai: AIClient, settings: Settings) -> AnalysisOutcome:
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
            raw = await asyncio.wait_for(
                ai.run(settings.ai_model, inputs), timeout=settings.ai_timeout_seconds
            )
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
