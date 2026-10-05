"""Bounded parsing of monetary amounts and dates in source text (per page).

Replaces the old "delete spaces/dots and search a substring" matching, which found 123 inside
9 123,00 and lost the decimal point of 12.34. A number is a whole token in one of the supported
representations; an amount needs a currency marker next to it or a page-level currency
declaration (e.g. "Waluta: PLN" on an invoice). Percentages and zero-padded identifiers are never
amounts.

Supported numbers: 184 500,00 (space/NBSP/narrow-space groups, comma decimals), 184.500,00 (dot
groups, comma decimals required), 184,500.00 (comma groups), 1234,5 / 12.34 (plain decimals),
plain integers. Supported dates: 2026-03-12, 12.03.2026, 12 marca 2026, 12 March 2026,
March 12, 2026. Anything else is out of scope and simply not matched.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from pdf_insight.codes import CURRENCIES

_NUMBER = re.compile(
    r"""
    (?<![\d.,])
    (?P<num>
        \d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:,\d{1,2})?
      | \d{1,3}(?:\.\d{3})+,\d{1,2}
      | \d{1,3}(?:,\d{3})+(?:\.\d{1,2})?
      | \d+,\d{1,2}
      | \d+\.\d{1,2}
      | \d+
    )
    (?![\d]|[.,]\d|[ \u00a0]?%)
    """,
    re.VERBOSE,
)
_CURRENCY_AFTER = re.compile(r"^[ \u00a0]*(zł|złotych|PLN|EUR|euro|€|USD|\$|[A-Z]{3})(?![\w])")
_CURRENCY_BEFORE = re.compile(r"(PLN|EUR|€|USD|\$|[A-Z]{3})[ \u00a0]*$")
_PAGE_CURRENCY = re.compile(r"\b(?:Waluta|Currency)\s*:\s*([A-Z]{3})\b")
_ALIASES = {"zł": "PLN", "złotych": "PLN", "euro": "EUR", "€": "EUR", "$": "USD"}

PL_MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
    "października", "listopada", "grudnia",
)  # fmt: skip
EN_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
)  # fmt: skip
_MONTH_INDEX = {name: i + 1 for i, name in enumerate(PL_MONTHS)} | {
    name: i + 1 for i, name in enumerate(EN_MONTHS)
}
_MONTH_NAMES = "|".join(_MONTH_INDEX)
_DATES = (
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), ("y", "m", "d")),
    (re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)"), ("d", "m", "y")),
    (
        re.compile(rf"(?<!\d)(\d{{1,2}})\s+({_MONTH_NAMES})\s+(\d{{4}})(?!\d)", re.I),
        ("d", "M", "y"),
    ),
    (re.compile(rf"\b({_MONTH_NAMES})\s+(\d{{1,2}}),\s*(\d{{4}})(?!\d)", re.I), ("M", "d", "y")),
)


@dataclass(frozen=True)
class AmountToken:
    page: int
    value: Decimal
    currency: str | None
    text: str


def parse_number(raw: str) -> Decimal:
    cleaned = re.sub(r"[ \u00a0\u202f]", "", raw)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{1,2}", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", cleaned):
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def _currency(code: str) -> str | None:
    code = _ALIASES.get(code, _ALIASES.get(code.lower(), code))
    return code if code in CURRENCIES else None


def amounts_on_page(page: int, text: str) -> list[AmountToken]:
    declared = _PAGE_CURRENCY.search(text)
    page_currency = _currency(declared.group(1)) if declared else None
    tokens = []
    for match in _NUMBER.finditer(text):
        if re.match(r"0\d", match.group("num")):
            continue  # identifiers such as KRS 0000990114 are not amounts
        after = _CURRENCY_AFTER.match(text[match.end() : match.end() + 12])
        before = _CURRENCY_BEFORE.search(text[max(0, match.start() - 6) : match.start()])
        currency = None
        if after:
            currency = _currency(after.group(1))
        if currency is None and before:
            currency = _currency(before.group(1))
        tokens.append(
            AmountToken(
                page,
                parse_number(match.group("num")),
                currency or page_currency,
                match.group("num"),
            )
        )
    return tokens


def dates_on_page(text: str) -> set[str]:
    found = set()
    for pattern, order in _DATES:
        for match in pattern.finditer(text):
            parts = dict(zip(order, match.groups(), strict=True))
            month = _MONTH_INDEX[parts["M"].lower()] if "M" in parts else int(parts["m"])
            day, year = int(parts["d"]), int(parts["y"])
            if 1 <= month <= 12 and 1 <= day <= 31:
                found.add(f"{year:04d}-{month:02d}-{day:02d}")
    return found


def as_decimal(value: float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def amount_in_source(value: float, source: str, currency: str | None = None) -> bool:
    """True when ``value`` occurs as a whole number token (with ``currency`` if given)."""
    target = as_decimal(value)
    return any(
        as_decimal(token.value) == target and (currency is None or token.currency == currency)
        for token in amounts_on_page(0, source)
    )


def date_in_source(iso: str, source: str) -> bool:
    return iso in dates_on_page(source)
