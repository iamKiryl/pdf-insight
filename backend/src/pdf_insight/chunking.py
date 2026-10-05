"""Page-aware chunking for chunked extraction (experimental mode, see docs/CHUNKING.md).

Chunks are built in source order from readable pages only (pages without a text layer are listed
separately and never sent). Nothing is truncated: every character of every readable page is in
exactly one chunk (plus a bounded overlap when a page is split).

Phase 1 packs whole pages; a page longer than CHUNK_MAX_CHARS is split at a paragraph, line or
whitespace boundary (searched in the last BOUNDARY_WINDOW characters) and each continuation
repeats up to CHUNK_OVERLAP_CHARS of the preceding text so a fact cut by the split is still seen
whole. If phase 1 needs more than MAX_CHUNKS chunks, phase 2 fills every chunk (splitting pages
where needed) and only closes a chunk with less than BOUNDARY_WINDOW characters of space left.
Every closed chunk then holds at least CHUNK_MAX - BOUNDARY_WINDOW - CHUNK_OVERLAP = 8 700
characters, of which at most CHUNK_OVERLAP (one leading continuation) repeat earlier text, i.e.
at least 8 400 new characters; 7 closed chunks plus a last chunk of up to 9 700 new characters
cover 68 500 >= MAX_CHUNKED_CHARS = 64 000, so the envelope always fits in MAX_CHUNKS = 8
(property-tested in tests/test_chunking.py).
"""

from dataclasses import dataclass

from .contract import AnalyzeRequest, has_letter

CHUNK_MAX_CHARS = 10_000
CHUNK_OVERLAP_CHARS = 300
BOUNDARY_WINDOW = 1_000
MAX_CHUNKS = 8
MAX_CHUNKED_CHARS = 64_000  # request text envelope; equals contract.MAX_TOTAL_CHARS


class TooManyChunks(Exception):
    pass


@dataclass(frozen=True)
class Segment:
    page: int
    start: int  # offset of the new (non-overlap) text in the page
    end: int
    overlap: str  # repeated tail of the previous part of the same page ("" if none)
    new_text: str

    @property
    def text(self) -> str:
        return self.overlap + self.new_text

    @property
    def size(self) -> int:
        return len(self.overlap) + len(self.new_text)


@dataclass(frozen=True)
class Chunk:
    index: int  # 1-based
    segments: tuple[Segment, ...]

    @property
    def size(self) -> int:
        return sum(s.size for s in self.segments)

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(dict.fromkeys(s.page for s in self.segments))


def cut_point(text: str, start: int, limit: int) -> int:
    """Largest boundary <= start + limit, preferring paragraph, line, then whitespace breaks in
    the last BOUNDARY_WINDOW characters; a hard cut only when there is no boundary at all."""
    end = start + limit
    if end >= len(text):
        return len(text)
    low = max(start + 1, end - BOUNDARY_WINDOW)
    for separator in ("\n\n", "\n", " "):
        position = text.rfind(separator, low, end)
        if position != -1:
            return position + len(separator)
    return end


def overlap_before(text: str, start: int) -> str:
    """Up to CHUNK_OVERLAP_CHARS of text before ``start``, beginning at a word boundary."""
    if start == 0:
        return ""
    tail_start = max(0, start - CHUNK_OVERLAP_CHARS)
    space = text.find(" ", tail_start, start)
    if tail_start > 0 and space != -1:
        tail_start = space + 1
    return text[tail_start:start]


def _readable(request: AnalyzeRequest) -> list[tuple[int, str]]:
    return [(p.page, p.text) for p in request.pages if has_letter(p.text)]


def _split_page(page: int, text: str) -> list[Segment]:
    segments, start = [], 0
    while start < len(text):
        overlap = overlap_before(text, start)
        end = cut_point(text, start, CHUNK_MAX_CHARS - len(overlap))
        segments.append(Segment(page, start, end, overlap, text[start:end]))
        start = end
    return segments


def _pack_whole_pages(pages: list[tuple[int, str]]) -> list[list[Segment]]:
    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    for page, text in pages:
        for segment in _split_page(page, text):
            if current and sum(s.size for s in current) + segment.size > CHUNK_MAX_CHARS:
                chunks.append(current)
                current = []
            current.append(segment)
    if current:
        chunks.append(current)
    return chunks


def _fill(pages: list[tuple[int, str]]) -> list[list[Segment]]:
    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0
    for page, text in pages:
        start = 0
        while start < len(text):
            overlap = overlap_before(text, start) if start else ""
            space = CHUNK_MAX_CHARS - used - len(overlap)
            remaining = len(text) - start
            if remaining <= space:
                current.append(Segment(page, start, len(text), overlap, text[start:]))
                used += len(overlap) + remaining
                break
            if space < BOUNDARY_WINDOW:
                chunks.append(current)
                current, used = [], 0
                continue
            end = cut_point(text, start, space)
            current.append(Segment(page, start, end, overlap, text[start:end]))
            chunks.append(current)
            current, used = [], 0
            start = end
    if current:
        chunks.append(current)
    return chunks


def build_chunks(request: AnalyzeRequest) -> list[Chunk]:
    pages = _readable(request)
    if sum(len(text) for _, text in pages) > MAX_CHUNKED_CHARS:
        raise TooManyChunks
    packed = _pack_whole_pages(pages)
    if len(packed) > MAX_CHUNKS:
        packed = _fill(pages)
    if len(packed) > MAX_CHUNKS:  # unreachable for inputs within the envelope (see module doc)
        raise TooManyChunks
    return [Chunk(i, tuple(segments)) for i, segments in enumerate(packed, start=1)]
