"""Chunk building: order, provenance, bounded overlap, no truncation, envelope (no model calls)."""

import random

import pytest

from pdf_insight.chunking import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
    MAX_CHUNKED_CHARS,
    MAX_CHUNKS,
    TooManyChunks,
    build_chunks,
)
from pdf_insight.contract import AnalyzeRequest, has_letter


def request_for(texts: list[str]) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate({
        "fileName": "d.pdf",
        "pageCount": len(texts),
        "pages": [{"page": i, "text": t} for i, t in enumerate(texts, start=1)],
        "pagesWithoutText": [i for i, t in enumerate(texts, start=1) if not has_letter(t)],
    })  # fmt: skip


def words(rng: random.Random, n: int) -> str:
    out, size = [], 0
    while size < n:
        piece = rng.choice(["umowa", "kwota", "zł", "netto", "termin", "Strona", "ąęś"])
        piece += rng.choice([" ", " ", " ", "\n", "\n\n", ", "])
        out.append(piece)
        size += len(piece)
    return "".join(out)[:n]


def assert_invariants(texts: list[str], chunks) -> None:
    assert 1 <= len(chunks) <= MAX_CHUNKS
    rebuilt: dict[int, str] = {}
    last = (0, 0)
    for chunk in chunks:
        assert chunk.size <= CHUNK_MAX_CHARS
        for seg in chunk.segments:
            assert (seg.page, seg.start) > last  # source order
            last = (seg.page, seg.start)
            page_text = texts[seg.page - 1]
            assert len(seg.overlap) <= CHUNK_OVERLAP_CHARS
            assert page_text[: seg.start].endswith(seg.overlap)  # overlap repeats preceding text
            assert seg.start == len(rebuilt.get(seg.page, ""))  # contiguous
            rebuilt[seg.page] = rebuilt.get(seg.page, "") + seg.new_text
    for number, text in enumerate(texts, start=1):
        if has_letter(text):
            assert rebuilt[number] == text  # nothing truncated
        else:
            assert number not in rebuilt  # pages without text are never sent


def test_small_document_is_one_chunk_with_whole_pages():
    texts = ["Strona pierwsza z treścią umowy.", "", "Strona trzecia, kwota 100 zł."]
    chunks = build_chunks(request_for(texts))
    assert len(chunks) == 1
    assert [s.page for s in chunks[0].segments] == [1, 3]
    assert all(s.overlap == "" for s in chunks[0].segments)


def test_whole_pages_are_packed_in_order():
    texts = ["a" * 6_000 + " koniec", "b" * 6_000 + " koniec", "c" * 3_000 + " koniec"]
    chunks = build_chunks(request_for(texts))
    assert [c.pages for c in chunks] == [(1,), (2, 3)]
    assert_invariants(texts, chunks)


def test_oversized_page_is_split_at_a_paragraph_boundary_with_overlap():
    first = ("Akapit pierwszy. " * 550).strip()  # ~9.35k chars: paragraph break inside the window
    second = ("Akapit drugi z kwotą 1 450 EUR netto. " * 250).strip()  # ~9.5k chars
    text = first + "\n\n" + second
    chunks = build_chunks(request_for([text]))
    assert len(chunks) >= 2
    assert chunks[0].segments[0].new_text.endswith("\n\n")  # cut right after the paragraph
    continuation = chunks[1].segments[0]
    assert 0 < len(continuation.overlap) <= CHUNK_OVERLAP_CHARS
    assert_invariants([text], chunks)


def test_text_beyond_the_old_single_call_limit_is_chunked_not_truncated():
    rng = random.Random(7)
    texts = [words(rng, 4_000) for _ in range(15)]  # 60 000 chars > 48 000
    chunks = build_chunks(request_for(texts))
    assert_invariants(texts, chunks)


def test_envelope_is_rejected_explicitly_beyond_the_limit():
    texts = ["x" * 20_000 for _ in range(3)] + ["y" * 4_001]  # 64 001 chars
    with pytest.raises(TooManyChunks):
        build_chunks(request_for(texts))


@pytest.mark.parametrize("seed", range(40))
def test_any_input_within_the_envelope_fits_in_max_chunks(seed):
    rng = random.Random(seed)
    texts, total = [], 0
    while total < MAX_CHUNKED_CHARS:
        size = rng.choice(
            [rng.randint(1, 800), rng.randint(800, 6_000), rng.randint(9_000, 20_000)]
        )
        size = min(size, MAX_CHUNKED_CHARS - total, 20_000)
        if size <= 0:
            break
        text = words(rng, size) if rng.random() < 0.8 else "x" * size  # no boundaries at all
        if rng.random() < 0.05:
            text = "  12  "[:size] if size >= 1 else text  # page without letters
        texts.append(text)
        total += len(text)
    assert_invariants(texts, build_chunks(request_for(texts)))
