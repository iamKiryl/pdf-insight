"""Pydantic models for the public API contract (mirrors frontend Zod schema and contracts/)."""

import datetime as dt
import re
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .codes import CURRENCIES, LANGUAGES
from .sentences import sentence_count_within

MAX_PAGES = 500
MAX_PAGE_CHARS = 20_000
MAX_TOTAL_CHARS = 48_000
MIN_TOTAL_LETTERS = 200
SUMMARY_SENTENCES = (3, 5)
KEY_POINTS = (3, 7)
MAX_KEYWORDS = 20

DocumentType = Literal["faktura", "umowa", "oferta", "raport", "inne"]
DOCUMENT_TYPES: tuple[str, ...] = ("faktura", "umowa", "oferta", "raport", "inne")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FORBIDDEN_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]")


def has_letter(text: str) -> bool:
    """A page "has text" when it contains at least one Unicode letter (same rule as frontend)."""
    return any(ch.isalpha() for ch in text)


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _iso_date(value: str) -> str:
    if not _ISO_DATE.match(value):
        raise ValueError("must be an ISO 8601 date YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be a valid calendar date") from exc
    return value


def _language(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError("must be a lowercase ISO 639-1 code")
    return value


def _currency(value: str) -> str:
    if value not in CURRENCIES:
        raise ValueError("must be an uppercase ISO 4217 code")
    return value


def _summary(value: str) -> str:
    if not sentence_count_within(value, *SUMMARY_SENTENCES):
        raise ValueError("must contain 3-5 sentences ending with punctuation")
    return value


def _file_name(value: str) -> str:
    if _FORBIDDEN_FILENAME_CHARS.search(value):
        raise ValueError("must not contain control characters or path separators")
    return value


def Text(max_length: int) -> type[str]:
    return Annotated[str, Field(min_length=1, max_length=max_length), AfterValidator(_not_blank)]  # type: ignore[return-value]


IsoDate = Annotated[str, AfterValidator(_iso_date)]
Language = Annotated[str, AfterValidator(_language)]
Currency = Annotated[str, AfterValidator(_currency)]
Fact = Text(500)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# ---------------------------------------------------------------- request


class PageText(_Strict):
    page: int = Field(ge=1)
    text: str = Field(max_length=MAX_PAGE_CHARS)


class AnalyzeRequest(_Strict):
    fileName: Annotated[Text(255), AfterValidator(_file_name)]
    pageCount: int = Field(ge=1, le=MAX_PAGES)
    pages: list[PageText] = Field(max_length=MAX_PAGES)
    pagesWithoutText: list[int] = Field(max_length=MAX_PAGES)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(self.pages) != self.pageCount:
            raise ValueError("pages must contain exactly pageCount items")
        if [p.page for p in self.pages] != list(range(1, self.pageCount + 1)):
            raise ValueError("page numbers must be 1..pageCount in order")
        expected = [p.page for p in self.pages if not has_letter(p.text)]
        if self.pagesWithoutText != expected:
            raise ValueError("pagesWithoutText does not match page texts")
        return self

    @property
    def total_chars(self) -> int:
        return sum(len(p.text) for p in self.pages)

    @property
    def total_letters(self) -> int:
        return sum(1 for p in self.pages for ch in p.text if ch.isalpha())


# ---------------------------------------------------------------- response


class DocumentInfo(_Strict):
    fileName: Text(255)
    pages: int = Field(ge=1)
    language: Language
    type: DocumentType
    title: Text(300)
    date: IsoDate | None


class Entities(_Strict):
    organizations: list[Fact]
    people: list[Fact]


class Amount(_Strict):
    value: float = Field(allow_inf_nan=False)
    currency: Currency
    context: Fact


class DateFact(_Strict):
    date: IsoDate
    context: Fact


class AnalysisInfo(_Strict):
    complete: bool
    pagesWithoutText: list[int]
    titleFallback: bool


class AnalysisResult(_Strict):
    document: DocumentInfo
    summary: Annotated[Text(2000), AfterValidator(_summary)]
    keyPoints: list[Fact] = Field(min_length=KEY_POINTS[0], max_length=KEY_POINTS[1])
    entities: Entities
    amounts: list[Amount]
    dates: list[DateFact]
    keywords: list[Fact] = Field(max_length=MAX_KEYWORDS)
    analysis: AnalysisInfo | None = None

    @model_validator(mode="after")
    def _analysis_consistent(self) -> Self:
        info = self.analysis
        if info is None:
            return self
        pages = info.pagesWithoutText
        if pages != sorted(set(pages)) or any(p < 1 or p > self.document.pages for p in pages):
            raise ValueError("pagesWithoutText must be ascending, unique and within 1..pages")
        if info.complete != (not pages):
            raise ValueError("analysis.complete must be true iff no pages lack text")
        return self
