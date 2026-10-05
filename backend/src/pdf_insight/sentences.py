"""Conservative sentence counting shared with the frontend (see contracts/README.md).

Naive splitting on "." miscounts "sp. z o.o.", "S.A.", "1.5" or "12.03.2026 r.". Instead of
guessing, we compute an interval: ambiguous boundaries count as non-boundaries for ``min`` and as
boundaries for ``max``. A summary is accepted when the interval intersects the allowed range.
"""

import re
from dataclasses import dataclass

ABBREVIATIONS: frozenset[str] = frozenset(
    {
        # Polish
        "al", "art", "dr", "godz", "hab", "inż", "itd", "itp", "lit", "mgr", "mld", "mln", "nr",
        "np", "ok", "pkt", "pn", "por", "poz", "prof", "pt", "r", "sp", "sz", "tj", "tys", "ul",
        "ust", "wg", "ww", "zob",
        # English
        "approx", "ca", "co", "corp", "dept", "etc", "fig", "inc", "jr", "ltd", "mr", "mrs", "ms",
        "no", "sr", "st", "vs",
    }
)  # fmt: skip

_TERMINAL = ".!?…"
_CLOSERS = "\"'”’»)]"  # noqa: RUF001 - typographic quotes are intended
_OPENERS = "\"'„“«(["
_CANDIDATE = re.compile(
    rf"([{re.escape(_TERMINAL)}]+)[{re.escape(_CLOSERS)}]*\s+[{re.escape(_OPENERS)}]*(\S)"
)
_ENDS_WITH_TERMINAL = re.compile(rf"[{re.escape(_TERMINAL)}][{re.escape(_CLOSERS)}]*$")
_TOKEN_BEFORE = re.compile(r"([^\W\d_]|\.)+$")


@dataclass(frozen=True)
class SentenceCount:
    min: int
    max: int
    valid: bool


def _is_ambiguous_token(text_before_dot: str) -> bool:
    match = _TOKEN_BEFORE.search(text_before_dot)
    if match is None:
        return False
    token = match.group(0).strip(".").lower()
    if not token:
        return False
    return len(token) == 1 or "." in token or token in ABBREVIATIONS


def count_sentences(text: str) -> SentenceCount:
    stripped = text.strip()
    if not stripped:
        return SentenceCount(0, 0, False)
    definite = 0
    ambiguous = 0
    for match in _CANDIDATE.finditer(stripped):
        run = match.group(1)
        next_char = match.group(2)
        if next_char.isdigit():
            ambiguous += 1
        elif next_char.isupper():
            if run == "." and _is_ambiguous_token(stripped[: match.start(1)]):
                ambiguous += 1
            else:
                definite += 1
    valid = _ENDS_WITH_TERMINAL.search(stripped) is not None
    return SentenceCount(definite + 1, definite + ambiguous + 1, valid)


def sentence_count_within(text: str, low: int, high: int) -> bool:
    result = count_sentences(text)
    return result.valid and result.min <= high and result.max >= low
