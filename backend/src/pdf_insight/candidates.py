"""Candidate occurrences of monetary amounts and dates, extracted by code (AI_MODE=compact).

Every candidate is an exact occurrence in the source: page, offsets of the number/date token,
the parsed value and a context excerpt copied from the source. The model only selects candidate
IDs; amounts, dates and contexts in the result are assembled from these candidates, so the model
can neither retype a value nor rewrite a context. Candidates are NOT facts: injected text, page
footers or repeated mentions are candidates too, and the model must choose.

Rules (generic, bounded; no document-specific names, values or page numbers):
- Amount: a bounded number token (pdf_insight.numbers) with a currency marker next to it, or —
  only for tokens with a two-digit decimal fraction (e.g. 55 350,00) — the page's explicit
  "Waluta:"/"Currency:" declaration. Integers without an adjacent currency (quantities, page
  numbers, IDs, years) and percentages are never amounts.
- Date: every day-month-year occurrence (pdf_insight.numbers formats) with its offsets.
- Context, copied from the source (whitespace collapsed) and prefixed with the page number:
  * table row ("|", or two or more money/date cells with at most 2 words per cell + 2): the row
    plus the
    nearest preceding column header (no numbers, three or more mostly capitalised words or "|",
    not ending like a sentence, within HEADER_LINES lines);
  * short label line ("Termin płatności: 29.03.2026"): the line plus the nearest preceding
    section heading (starting with two upper-case words, within HEADING_LINES lines);
  * prose: the sentence (PDF line breaks are not boundaries; blank lines are) bounded to WINDOW
    characters each side.
  A context is never longer than the public 500-character limit; the window may cut a very long
  sentence (a qualifier more than WINDOW characters away is then not shown) — a documented limit.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .contract import AnalyzeRequest, has_letter
from .numbers import _NUMBER, amounts_on_page, date_occurrences

WINDOW = 190
HEADER_LINES = 8
HEADING_LINES = 10
SHORT_LINE = 80
PREFIX_MAX = 90
CONTEXT_MAX = 500
MAX_CANDIDATES = 400

# Sentence end in prose: punctuation, whitespace, then an upper-case letter. PDF line breaks inside
# a sentence are not boundaries ("tj. 28 800" or "r. (dalej" do not end a sentence).
_SENTENCE_END = re.compile(r"[.!?;]\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])|\n[ \t]*\n")  # also blank lines
_HEADING = re.compile(r"^\s*[A-ZĄĆĘŁŃÓŚŹŻ]{3,}(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ]+)+\b")
_TWO_DECIMALS = re.compile(r"[.,]\d{2}$")


class TooManyCandidates(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    id: int
    kind: Literal["amount", "date"]
    page: int
    start: int
    end: int
    context: str  # source excerpt (with page prefix), copied into the public result
    value: Decimal | None = None
    currency: str | None = None
    date: str | None = None


def _sentence(text: str, start: int, end: int) -> str:
    """Prose context: the sentence around [start, end), line breaks treated as spaces, bounded to
    WINDOW characters each side (cut at a word boundary when the sentence is longer)."""
    low = max(0, start - WINDOW)
    left = low
    for match in _SENTENCE_END.finditer(text, low, start):
        left = match.end()
    stop = _SENTENCE_END.search(text, end, min(len(text), end + WINDOW))
    right = stop.start() + 1 if stop else min(len(text), end + WINDOW)
    if left == low and low > 0:
        space = text.find(" ", left, start)
        left = space + 1 if space != -1 else left
    if not stop and right < len(text):
        space = text.rfind(" ", end, right)
        right = space if space != -1 else right
    return " ".join(text[left:right].split())


def _line_bounds(text: str, position: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return start, (end if end != -1 else len(text))


def _preceding_line(text: str, line_start: int, limit: int, accept) -> str | None:
    lines = text[:line_start].split("\n")[:-1] if line_start else []
    for line in reversed(lines[-limit:]):
        if accept(line):
            return " ".join(line.split())
    return None


def _is_header(line: str) -> bool:
    """Column header: no numbers, at least three words, not a sentence (no closing punctuation),
    and either "|" separators or mostly capitalised words."""
    words = line.split()
    if len(words) < 3 or _NUMBER.search(line) or not has_letter(line):
        return False
    if line.rstrip().endswith((".", ":", ";", ",")):
        return False
    capitalised = sum(1 for w in words if w[:1].isupper())
    return "|" in line or capitalised * 2 >= len(words)


def _is_table_row(line: str) -> bool:
    """A "|" separator, or at least two money/date cells with few words per cell (a prose line
    that mentions two amounts has many words and is read as a sentence instead)."""
    if "|" in line:
        return True
    money = sum(1 for t in amounts_on_page(0, line)
                if t.adjacent_currency or _TWO_DECIMALS.search(t.text))  # fmt: skip
    cells = money + len(date_occurrences(line))
    words = sum(1 for w in line.split() if any(ch.isalpha() for ch in w))
    return cells >= 2 and words <= 2 * cells + 2


def _context(text: str, page: int, start: int, end: int) -> str:
    line_start, line_end = _line_bounds(text, start)
    line = " ".join(text[line_start:line_end].split())
    if _is_table_row(line):  # table row: the row plus its column header
        prefix = _preceding_line(text, line_start, HEADER_LINES, _is_header)
        excerpt = line
    elif len(line) <= SHORT_LINE and ":" in text[line_start:start]:  # label line: + heading
        prefix = _preceding_line(text, line_start, HEADING_LINES,
                                 lambda ln: bool(_HEADING.match(ln)))  # fmt: skip
        excerpt = line
    else:  # prose
        prefix, excerpt = None, _sentence(text, start, end)
    if prefix:
        if len(prefix) > PREFIX_MAX:
            prefix = prefix[:PREFIX_MAX].rsplit(" ", 1)[0] + " …"
        excerpt = f"{prefix} | {excerpt}"
    context = f"s. {page}: {excerpt}"
    if len(context) > CONTEXT_MAX:  # long table row: keep the token, never exceed the contract
        context = context[: CONTEXT_MAX - 2].rsplit(" ", 1)[0] + " …"
    return context


def extract_candidates(request: AnalyzeRequest) -> list[Candidate]:
    found: list[tuple[int, int, str, Decimal | None, str | None, str | None, int]] = []
    for page in request.pages:
        if not has_letter(page.text):
            continue
        text = page.text
        declared = re.search(r"\b(?:Waluta|Currency)\s*:\s*[A-Z]{3}\b", text) is not None
        for token in amounts_on_page(page.page, text):
            if token.currency is None:
                continue
            adjacent = token.adjacent_currency
            if not adjacent and not (declared and _TWO_DECIMALS.search(token.text)):
                continue  # page-level currency only for decimal money values
            found.append((page.page, token.start, "amount", token.value, token.currency, None,
                          token.end))  # fmt: skip
        for iso, start, end in date_occurrences(text):
            found.append((page.page, start, "date", None, None, iso, end))
    if len(found) > MAX_CANDIDATES:
        raise TooManyCandidates
    found.sort(key=lambda f: (f[0], f[1]))
    texts = {p.page: p.text for p in request.pages}
    return [
        Candidate(
            id=i, kind=kind, page=page, start=start, end=end,  # type: ignore[arg-type]
            context=_context(texts[page], page, start, end),
            value=value, currency=currency, date=iso,
        )
        for i, (page, start, kind, value, currency, iso, end) in enumerate(found, start=1)
    ]  # fmt: skip
