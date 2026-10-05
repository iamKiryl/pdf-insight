"""Validation, evidence grounding and deterministic merging of chunk outputs (pure functions).

Merge rules (docs/CHUNKING.md):
- A fact is kept only if its quoted evidence occurs in one of the chunk's pages (after whitespace,
  quote and dash normalisation) and the value/date occurs in that evidence. The page is taken from
  where the evidence is found, not from the model. Ungrounded facts are dropped and counted.
- Amounts are never added up and never merged across currency, basis, period or status. Two
  entries collapse only when everything matches AND their evidence spans overlap on the same page
  (the same text seen twice, e.g. through chunk overlap). Equal values elsewhere stay separate.
- Dated events collapse only for the same date with overlapping evidence on one page, or the same
  date with the same normalised event text. Different events on one date stay separate.
- Chunk outputs are data: nothing in them is ever sent back to the model or executed.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .analyzer import InvalidModelOutput, _clean_list, _describe, fallback_title
from .chunk_prompt import AmountBasis, AmountPeriod, AmountStatus
from .chunking import Chunk
from .codes import CURRENCIES
from .contract import (
    KEY_POINTS,
    AnalysisInfo,
    AnalysisResult,
    AnalyzeRequest,
    DocumentType,
    IsoDate,
    Language,
    Text,
)
from .numbers import amounts_on_page, as_decimal, dates_on_page
from .sentences import sentence_count_within

MAX_EVIDENCE_CHARS = 300
MAX_KEYWORDS_OUT = 12


class _Raw(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class ChunkAmount(_Raw):
    value: float = Field(allow_inf_nan=False)
    currency: Annotated[str, Field(min_length=3, max_length=3)]
    basis: AmountBasis
    period: AmountPeriod
    status: AmountStatus
    context: Text(500)
    page: int = Field(ge=1)
    evidence: Text(MAX_EVIDENCE_CHARS)


class ChunkDate(_Raw):
    date: IsoDate
    event: Text(500)
    page: int = Field(ge=1)
    evidence: Text(MAX_EVIDENCE_CHARS)


class ChunkOutput(_Raw):
    amounts: list[ChunkAmount]
    dates: list[ChunkDate]
    organizations: list[str]
    people: list[str]
    keywords: list[str]


class OverviewOutput(_Raw):
    insufficientContent: bool
    language: Language
    type: DocumentType
    title: str | None
    date: IsoDate | None
    summary: str
    keyPoints: list[str]
    keywords: list[str]


def parse_chunk_output(payload: dict[str, Any]) -> ChunkOutput:
    try:
        output = ChunkOutput.model_validate(payload)
    except ValidationError as exc:
        raise InvalidModelOutput(_describe(exc)) from None
    bad = [
        f"amounts.{i}.currency: must be an ISO 4217 code"
        for i, a in enumerate(output.amounts)
        if a.currency.upper() not in CURRENCIES
    ]
    if bad:
        raise InvalidModelOutput(bad)
    return output


def parse_overview(payload: dict[str, Any]) -> OverviewOutput:
    """Validate the overview including summary/keyPoints bounds, so a retry targets this call."""
    if isinstance(payload, dict) and isinstance(payload.get("language"), str):
        payload = {**payload, "language": payload["language"].strip().lower()}
    try:
        overview = OverviewOutput.model_validate(payload)
    except ValidationError as exc:
        raise InvalidModelOutput(_describe(exc)) from None
    if overview.insufficientContent:
        return overview
    problems = []
    if not sentence_count_within(overview.summary.strip(), 3, 5):
        problems.append("summary: must contain 3-5 sentences ending with punctuation")
    points = _clean_list(overview.keyPoints)
    if not KEY_POINTS[0] <= len(points) <= KEY_POINTS[1]:
        problems.append(f"keyPoints: need {KEY_POINTS[0]}-{KEY_POINTS[1]} non-empty distinct items")
    if problems:
        raise InvalidModelOutput(problems)
    return overview


# ------------------------------------------------------------------ grounding

# Typographic quotes, dashes and non-breaking spaces compared as their ASCII equivalents.
_QUOTES = str.maketrans(
    {
        "\u201e": '"', "\u201d": '"', "\u201c": '"', "\u00ab": '"', "\u00bb": '"',
        "\u2019": "'", "\u2018": "'", "\u2013": "-", "\u2014": "-", "\u00a0": " ",
        "\u202f": " ",
    }
)  # fmt: skip


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass(frozen=True)
class GroundedAmount:
    value: float
    currency: str
    basis: str
    period: str
    status: str
    context: str
    page: int
    start: int  # position of the evidence in the normalised page text
    end: int
    chunk: int


@dataclass(frozen=True)
class GroundedDate:
    date: str
    event: str
    page: int
    start: int
    end: int
    chunk: int


@dataclass
class GroundedChunk:
    amounts: list[GroundedAmount] = field(default_factory=list)
    dates: list[GroundedDate] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    dropped: int = 0


def _locate(evidence: str, preferred: int, chunk: Chunk, pages: dict[int, str]):
    """Find the evidence in the chunk's segments; return (page, start, end) in the normalised page
    text, or None. The model's page is tried first, then the other pages of the chunk."""
    needle = normalize(evidence)
    if len(needle) < 3:
        return None
    candidates = [preferred] + [p for p in chunk.pages if p != preferred]
    for page in candidates:
        if page not in chunk.pages:
            continue
        segment_text = " ".join(s.text for s in chunk.segments if s.page == page)
        if needle in normalize(segment_text):
            start = pages[page].find(needle)
            if start != -1:
                return page, start, start + len(needle)
    return None


def ground_chunk(request: AnalyzeRequest, chunk: Chunk, output: ChunkOutput) -> GroundedChunk:
    pages = {p.page: normalize(p.text) for p in request.pages}
    grounded = GroundedChunk(
        organizations=_clean_list(output.organizations),
        people=_clean_list(output.people),
        keywords=_clean_list(output.keywords),
    )
    for amount in output.amounts:
        where = _locate(amount.evidence, amount.page, chunk, pages)
        tokens = amounts_on_page(0, amount.evidence) if where else []
        matching = [t for t in tokens if as_decimal(t.value) == as_decimal(amount.value)]
        currency = amount.currency.upper()
        if not where or not matching or any(t.currency not in (None, currency) for t in matching):
            grounded.dropped += 1
            continue
        page, start, end = where
        grounded.amounts.append(GroundedAmount(
            amount.value, currency, amount.basis, amount.period, amount.status,
            amount.context.strip(), page, start, end, chunk.index,
        ))  # fmt: skip
    for date in output.dates:
        where = _locate(date.evidence, date.page, chunk, pages)
        if not where or date.date not in dates_on_page(date.evidence):
            grounded.dropped += 1
            continue
        page, start, end = where
        grounded.dates.append(
            GroundedDate(date.date, date.event.strip(), page, start, end, chunk.index)
        )
    return grounded


# ------------------------------------------------------------------ merging

LABELS: dict[str, dict[str, str]] = {
    "pl": {"net": "netto", "gross": "brutto", "vat": "VAT", "one-off": "jednorazowo",
           "monthly": "miesięcznie", "yearly": "rocznie", "daily": "za dzień",
           "rejected": "odrzucona", "historical": "historyczna", "proposed": "proponowana",
           "estimated": "szacunkowa", "budget": "budżet", "maximum": "maksymalnie"},
    "en": {"net": "net", "gross": "gross", "vat": "VAT", "one-off": "one-off",
           "monthly": "monthly", "yearly": "yearly", "daily": "per day", "rejected": "rejected",
           "historical": "historical", "proposed": "proposed", "estimated": "estimated",
           "budget": "budget", "maximum": "maximum"},
}  # fmt: skip
_MENTIONED: dict[str, str] = {
    "net": r"\bnett?o?\b|\bnet\b", "gross": r"brutto|gross", "vat": r"\bvat\b|podat",
    "one-off": r"jednoraz|one-off|one time", "monthly": r"mies|month",
    "yearly": r"rocz|\brok|year|annual",
    "daily": r"dzie[nń]|dzienn|daily|per day", "rejected": r"odrzuc|reject",
    "historical": r"histor|wcześniej|previous", "proposed": r"propon|propos",
    "estimated": r"szacun|estimat", "budget": r"budżet|budget",
    "maximum": r"maks|nie więcej|limit|max",
}  # fmt: skip


def labelled_context(amount: GroundedAmount, language: str) -> str:
    """Append structured qualifiers that the free-text context does not already mention, in the
    document language (pl/en); other languages keep the model's context unchanged."""
    labels = LABELS.get(language)
    if labels is None:
        return amount.context
    missing = [
        labels[q] for q in (amount.basis, amount.period, amount.status)
        if q in labels and not re.search(_MENTIONED[q], amount.context.casefold())
    ]  # fmt: skip
    return f"{amount.context} ({', '.join(missing)})" if missing else amount.context


def _overlaps(a, b) -> bool:
    return a.page == b.page and a.start < b.end and b.start < a.end


def merge_amounts(chunks: list[GroundedChunk]) -> tuple[list[GroundedAmount], int]:
    kept: list[GroundedAmount] = []
    duplicates = 0
    for amount in (a for c in chunks for a in c.amounts):
        same = [
            k for k in kept
            if as_decimal(k.value) == as_decimal(amount.value) and k.currency == amount.currency
            and (k.basis, k.period, k.status) == (amount.basis, amount.period, amount.status)
            and _overlaps(k, amount)
        ]  # fmt: skip
        if same:
            duplicates += 1
            continue
        kept.append(amount)
    return sorted(kept, key=lambda a: (a.page, a.start, a.chunk)), duplicates


def merge_dates(chunks: list[GroundedChunk]) -> tuple[list[GroundedDate], int]:
    kept: list[GroundedDate] = []
    duplicates = 0
    for date in (d for c in chunks for d in c.dates):
        if any(k.date == date.date and (_overlaps(k, date) or normalize(k.event) ==
                                        normalize(date.event)) for k in kept):  # fmt: skip
            duplicates += 1
            continue
        kept.append(date)
    return sorted(kept, key=lambda d: (d.page, d.start, d.chunk)), duplicates


def merge_organizations(names: list[str]) -> list[str]:
    """Case-insensitive de-duplication; a name that is a word-prefix of a longer listed name
    (e.g. without its legal form) is dropped in favour of the longer one."""
    unique = _clean_list(names)
    keys = [normalize(n) for n in unique]
    return [
        name for name, key in zip(unique, keys, strict=True)
        if not any(other != key and other.startswith(key + " ") for other in keys)
    ]  # fmt: skip


@dataclass(frozen=True)
class MergeStats:
    dropped: int
    duplicate_amounts: int
    duplicate_dates: int


def merge(
    request: AnalyzeRequest, overview: OverviewOutput, chunks: list[GroundedChunk]
) -> tuple[AnalysisResult, MergeStats]:
    amounts, dup_amounts = merge_amounts(chunks)
    dates, dup_dates = merge_dates(chunks)
    language = overview.language
    title = (overview.title or "").strip()
    keywords = _clean_list(overview.keywords + [k for c in chunks for k in c.keywords])
    candidate = {
        "document": {
            "fileName": request.fileName.strip(),
            "pages": request.pageCount,
            "language": language,
            "type": overview.type,
            "title": title or fallback_title(language),
            "date": overview.date,
        },
        "summary": overview.summary.strip(),
        "keyPoints": _clean_list(overview.keyPoints),
        "entities": {
            "organizations": merge_organizations([o for c in chunks for o in c.organizations]),
            "people": _clean_list([p for c in chunks for p in c.people]),
        },
        "amounts": [
            {"value": a.value, "currency": a.currency, "context": labelled_context(a, language)}
            for a in amounts
        ],
        "dates": [{"date": d.date, "context": d.event} for d in dates],
        "keywords": keywords[:MAX_KEYWORDS_OUT],
        "analysis": AnalysisInfo(
            complete=not request.pagesWithoutText,
            pagesWithoutText=list(request.pagesWithoutText),
            titleFallback=not title,
        ).model_dump(),
    }
    try:
        result = AnalysisResult.model_validate(candidate)
    except ValidationError as exc:
        raise InvalidModelOutput(_describe(exc)) from None
    stats = MergeStats(sum(c.dropped for c in chunks), dup_amounts, dup_dates)
    return result, stats
