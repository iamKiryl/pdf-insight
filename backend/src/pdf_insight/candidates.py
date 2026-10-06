"""Candidate occurrences of monetary amounts and dates, extracted by code (AI_MODE=compact).

Every candidate is an exact occurrence in the source: page, offsets of the number/date token,
the parsed value and a context excerpt copied from the source. The model only selects candidate
IDs; amounts, dates and contexts in the result are assembled from these candidates, so the model
can neither retype a value nor rewrite a context. Candidates are NOT facts: injected text or
repeated mentions are candidates too, and the model must choose.

Rules (generic, bounded; no document-specific names, values or page numbers):
- Amount: a bounded number token (pdf_insight.numbers, including line-wrapped grouped numbers)
  with a currency marker next to it, or — only for tokens with a two-digit decimal fraction
  (e.g. 55 350,00) — the page's explicit "Waluta:"/"Currency:" declaration. Integers without an
  adjacent currency (quantities, page numbers, IDs, years) and percentages are never amounts.
- Date: every day-month-year occurrence (pdf_insight.numbers formats) with its offsets.
- Repeated page metadata: a line among the first/last EDGE_LINES lines of a page that recurs (digits
  ignored) on at least FOOTER_MIN_PAGES pages, carries a page-numbering or version marker
  ("Strona 3 z 12", "Page 3 of 12", "Wersja 1.3") and the same dates on every page is a running
  header/footer; its numbers and dates are not candidates. A dated event that merely repeats in
  the body is kept.

Context, copied from the source (whitespace collapsed), always formatted as
``s. {page}: [{header or heading}] {excerpt}`` (the bracketed part only when there is one), with
the selected occurrence — the number with its adjacent currency, or the date — wrapped as
»value« so that a sentence or row with several values identifies the selected one. »/« already
present in the source are replaced by '"', so the source cannot fake a selection.
  * table row ("|", or two or more money/date cells with at most 2 words per cell + 2, currency
    words not counted, no sentence break inside): the row, with the nearest column header above;
  * short label line ("Termin płatności: 29.03.2026"): the line, with the nearest section heading
    (starting with two upper-case words) within HEADING_LINES lines;
  * row of a flattened table: a line directly under a column header (no blank line, numbered
    paragraph or finished sentence in between, within HEADER_LINES lines): the line and header;
  * prose: the sentence (PDF line breaks are not boundaries; blank lines are) bounded to WINDOW
    characters each side.
  A column header: no numbers, three or more words, mostly capitalised or "|", not ending like a
  sentence, no dash (lines such as "Name — Role" are not headers). Whitespace-separated tables are
  not mapped to columns: the header and the marked cell are shown and the reader maps them.
  A context never exceeds the public 500-character limit: the header is capped, then the excerpt
  is cut around the marked occurrence at word boundaries, with a visible "…" on each cut side —
  the selected value and currency are always kept.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .contract import AnalyzeRequest, has_letter
from .numbers import (
    _CURRENCY_AFTER,
    _CURRENCY_BEFORE,
    _NUMBER,
    _currency,
    _wraps,
    amounts_on_page,
    date_occurrences,
)

WINDOW = 190
HEADER_LINES = 30  # long tables; the search stops where the table ends
HEADING_LINES = 10
SHORT_LINE = 80
ROW_MAX = 160
PREFIX_MAX = 90
CONTEXT_MAX = 500
MAX_CANDIDATES = 400
EDGE_LINES = 2
FOOTER_MIN_PAGES = 3
OPEN, CLOSE = "»", "«"

# A period after a single capital letter is an initial ("P. Dąbrowski"), not a sentence end.
_NOT_INITIAL = r"(?<![\s(\-][A-ZĄĆĘŁŃÓŚŹŻ])"
# Sentence end in prose: punctuation, whitespace, then an upper-case letter. PDF line breaks inside
# a sentence are not boundaries ("tj. 28 800" or "r. (dalej" do not end a sentence).
_SENTENCE_END = re.compile(  # also blank lines and a line starting a numbered paragraph ("2. ")
    rf"{_NOT_INITIAL}[.!?;]\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])|\n[ \t]*\n|\n(?=[ \t]*\d+\.\s)"
)
_SENTENCE_INSIDE = re.compile(rf"{_NOT_INITIAL}[.!?]\s+[A-ZĄĆĘŁŃÓŚŹŻ]")
_HEADING = re.compile(r"^\s*[A-ZĄĆĘŁŃÓŚŹŻ]{3,}(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ]+)+\b")
_PARAGRAPH = re.compile(r"^\s*\d+\.\s")
_TWO_DECIMALS = re.compile(r"[.,]\d{2}$")
_CURRENCY_WORDS = {"zł", "złotych", "pln", "eur", "euro", "€", "usd", "$"}
_PAGE_MARKER = re.compile(
    r"\b(?:strona|str\.|page|seite)\s*#+\s*(?:z|of|/|von)\s*#+|\b(?:wersja|version|ver\.|rev\.?)\s*#",
    re.IGNORECASE,
)


class TooManyCandidates(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    id: int
    kind: Literal["amount", "date"]
    page: int
    start: int
    end: int
    context: str  # source excerpt (with page prefix and »marked« occurrence), copied as is
    value: Decimal | None = None
    currency: str | None = None
    date: str | None = None


def _clean(text: str) -> str:
    return " ".join(text.replace(OPEN, '"').replace(CLOSE, '"').split())


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int, bool, bool]:
    """Prose bounds around [start, end): the sentence, line breaks treated as spaces, bounded to
    WINDOW characters each side (cut at a word boundary). Also says which sides were cut."""
    low = max(0, start - WINDOW)
    left = low
    for match in _SENTENCE_END.finditer(text, low, start):
        left = match.end()
    stop = _SENTENCE_END.search(text, end, min(len(text), end + WINDOW))
    right = stop.start() + 1 if stop else min(len(text), end + WINDOW)
    cut_left = left == low and low > 0
    if cut_left:
        space = text.find(" ", left, start)
        left = space + 1 if space != -1 else left
    cut_right = not stop and right < len(text)
    if cut_right:
        space = text.rfind(" ", end, right)
        right = space if space != -1 else right
    return left, right, cut_left, cut_right


def _line_bounds(text: str, position: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return start, (end if end != -1 else len(text))


def _preceding_lines(text: str, line_start: int, limit: int) -> list[str]:
    lines = text[:line_start].split("\n")[:-1] if line_start else []
    return list(reversed(lines[-limit:]))


def _is_header(line: str, above_row: bool = False) -> bool:
    """Column header: no numbers, at least three words, not a sentence (no closing punctuation),
    no dash, and either "|" separators or mostly capitalised words — or, directly above an
    explicit table row, any such line ("Etap Wartość netto etapu Rozliczona zaliczka (30%)")."""
    words = line.split()
    if len(words) < 3 or _NUMBER.search(line) or not has_letter(line):
        return False
    if line.rstrip().endswith((".", ":", ";", ",")) or "\u2014" in line or "\u2013" in line:
        return False
    capitalised = sum(1 for w in words if w[:1].isupper())
    return "|" in line or capitalised * 2 >= len(words) or (above_row and len(line) <= ROW_MAX)


def _header_above(text: str, line_start: int) -> str | None:
    """The nearest column header above, unless a blank line, a numbered paragraph or a finished
    sentence comes first (the table ended there)."""
    below = text[line_start : _line_bounds(text, line_start)[1]]
    for line in _preceding_lines(text, line_start, HEADER_LINES):
        if _is_header(line, above_row=_is_table_row(below)):
            return " ".join(line.split())
        if not line.strip() or _PARAGRAPH.match(line) or line.rstrip().endswith((".", "!", "?")):
            return None
        below = line
    return None


def _heading_above(text: str, line_start: int) -> str | None:
    for line in _preceding_lines(text, line_start, HEADING_LINES):
        if _HEADING.match(line):
            return " ".join(line.split())
    return None


def _is_table_row(line: str) -> bool:
    """A "|" separator, or at least two money/date cells with few words per cell and no sentence
    break inside (a prose line that mentions two amounts is read as a sentence instead)."""
    if "|" in line:
        return True
    if _SENTENCE_INSIDE.search(line):
        return False
    money = sum(1 for t in amounts_on_page(0, line)
                if t.adjacent_currency or _TWO_DECIMALS.search(t.text))  # fmt: skip
    cells = money + len(date_occurrences(line))
    words = sum(1 for w in line.split() if has_letter(w) and w.casefold() not in _CURRENCY_WORDS)
    return cells >= 2 and words <= 2 * cells + 2


def _occurrence(text: str, kind: str, start: int, end: int) -> tuple[int, int]:
    """The span to mark: a number with its adjacent currency marker, or the date."""
    if kind != "amount":
        return start, end
    after = _CURRENCY_AFTER.match(text[end : end + 12])
    if after and _currency(after.group(1)):
        return start, end + after.end()
    before = _CURRENCY_BEFORE.search(text[max(0, start - 6) : start])
    if before and _currency(before.group(1)):
        return start - (len(text[max(0, start - 6) : start]) - before.start()), end
    return start, end


def _bounds(
    text: str, start: int, end: int, wraps: list[tuple[int, int]]
) -> tuple[int, int, str | None, bool, bool]:
    """Excerpt bounds in the page text, the bracketed header/heading and which sides were cut.
    A line that a wrapped number crosses is prose continuing on the next line, never a row."""
    line_start, line_end = _line_bounds(text, start)
    line = text[line_start:line_end]
    crossed = any(a < line_end < b or a < line_start - 1 < b for a, b in wraps)
    on_line = end <= line_end and not crossed
    if on_line and _is_table_row(line):
        return line_start, line_end, _header_above(text, line_start), False, False
    if on_line and len(" ".join(line.split())) <= SHORT_LINE and ":" in text[line_start:start]:
        return line_start, line_end, _heading_above(text, line_start), False, False
    if on_line and len(line) <= ROW_MAX and not (_PARAGRAPH.match(line)
                                                  or _SENTENCE_INSIDE.search(line)):  # fmt: skip
        header = _header_above(text, line_start)
        sentence = line.rstrip().endswith(".") and len(line.split()) >= 8
        if header and not sentence:
            return line_start, line_end, header, False, False
    left, right, cut_left, cut_right = _sentence_bounds(text, start, end)
    return left, right, None, cut_left, cut_right


def _fit(page: int, prefix: str | None, before: str, value: str, after: str,
         cut_left: bool, cut_right: bool) -> str:  # fmt: skip
    """``s. {page}: [{prefix}] {before}»{value}«{after}`` within CONTEXT_MAX: cap the prefix, then
    cut the excerpt around the marked value (left side keeps up to 2/3 of the room: qualifiers
    and labels usually precede a value in Polish documents and tables)."""
    if prefix and len(prefix) > PREFIX_MAX:
        prefix = prefix[:PREFIX_MAX].rsplit(" ", 1)[0] + " …"
    head = f"s. {page}: " + (f"[{prefix}] " if prefix else "")
    marked = f"{OPEN}{value}{CLOSE}"
    room = CONTEXT_MAX - len(head) - len(marked) - 4  # two possible "… " / " …"
    if len(before) + len(after) > room:
        keep_left = min(len(before), max(room * 2 // 3, room - len(after)))
        keep_right = room - keep_left
        if keep_left < len(before):
            before = before[len(before) - keep_left :].split(" ", 1)[-1]
            cut_left = True
        if keep_right < len(after):
            after = after[:keep_right].rsplit(" ", 1)[0]
            cut_right = True
    before = ("… " if cut_left else "") + before
    after = after + (" …" if cut_right else "")
    return head + before + marked + after


def _context(
    text: str, page: int, kind: str, start: int, end: int, wraps: list[tuple[int, int]]
) -> str:
    left, right, prefix, cut_left, cut_right = _bounds(text, start, end, wraps)
    occ_start, occ_end = _occurrence(text, kind, start, end)
    occ_start, occ_end = max(left, occ_start), min(right, occ_end)
    before = _clean(text[left:occ_start])
    value = _clean(text[occ_start:occ_end])
    after = _clean(text[occ_end:right])
    before = before + " " if before and text[occ_start - 1].isspace() else before
    after = " " + after if after and text[occ_end].isspace() else after
    return _fit(page, prefix and _clean(prefix).replace("[", "(").replace("]", ")"), before,
                value, after, cut_left, cut_right)  # fmt: skip


def metadata_spans(request: AnalyzeRequest) -> dict[int, list[tuple[int, int]]]:
    """Line spans of repeated running headers/footers carrying page-numbering or version marks."""
    seen: dict[str, list[tuple[int, int, int, frozenset[str]]]] = defaultdict(list)
    for page in request.pages:
        if not has_letter(page.text):
            continue
        offsets, position = [], 0
        for line in page.text.split("\n"):
            if line.strip():
                offsets.append((position, position + len(line)))
            position += len(line) + 1
        edges = offsets[:EDGE_LINES] + offsets[-EDGE_LINES:]
        for start, end in dict.fromkeys(edges):
            line = page.text[start:end]
            key = re.sub(r"\d+", "#", " ".join(line.split()))
            if _PAGE_MARKER.search(key):
                dates = frozenset(iso for iso, _, _ in date_occurrences(line))
                seen[key].append((page.page, start, end, dates))
    spans: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for occurrences in seen.values():
        pages = {o[0] for o in occurrences}
        same_dates = len({o[3] for o in occurrences}) == 1
        if len(pages) >= FOOTER_MIN_PAGES and same_dates:
            for page_number, start, end, _ in occurrences:
                spans[page_number].append((start, end))
    return spans


def extract_candidates(request: AnalyzeRequest) -> list[Candidate]:
    found: list[tuple[int, int, str, Decimal | None, str | None, str | None, int]] = []
    metadata = metadata_spans(request)
    for page in request.pages:
        if not has_letter(page.text):
            continue
        text = page.text
        skip = metadata.get(page.page, [])

        def in_metadata(position: int) -> bool:
            return any(start <= position < end for start, end in skip)  # noqa: B023

        declared = re.search(r"\b(?:Waluta|Currency)\s*:\s*[A-Z]{3}\b", text) is not None
        for token in amounts_on_page(page.page, text):
            if token.currency is None or in_metadata(token.start):
                continue
            adjacent = token.adjacent_currency
            if not adjacent and not (declared and _TWO_DECIMALS.search(token.text)):
                continue  # page-level currency only for decimal money values
            found.append((page.page, token.start, "amount", token.value, token.currency, None,
                          token.end))  # fmt: skip
        for iso, start, end in date_occurrences(text):
            if not in_metadata(start):
                found.append((page.page, start, "date", None, None, iso, end))
    if len(found) > MAX_CANDIDATES:
        raise TooManyCandidates
    found.sort(key=lambda f: (f[0], f[1]))
    texts = {p.page: p.text for p in request.pages}
    wraps = {p.page: [(a, b) for a, b, _ in _wraps(p.text)[0]] for p in request.pages}
    return [
        Candidate(
            id=i, kind=kind, page=page, start=start, end=end,  # type: ignore[arg-type]
            context=_context(texts[page], page, kind, start, end, wraps[page]),
            value=value, currency=currency, date=iso,
        )
        for i, (page, start, kind, value, currency, iso, end) in enumerate(found, start=1)
    ]  # fmt: skip
