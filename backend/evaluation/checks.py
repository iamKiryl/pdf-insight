"""Atomic quality checks for one analysis result against a case's expected facts.

Every check is independent (one fact or one qualifier), so a report says exactly what is missing
instead of a single percentage. Checks never call the model.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any

# Qualifier vocabulary (Polish + English). A context "has" a qualifier when any pattern matches.
QUALIFIERS: dict[str, tuple[str, ...]] = {
    "net": (r"\bnetto\b", r"\bnet\b"),
    "gross": (r"\bbrutto\b", r"\bgross\b"),
    "vat": (r"\bvat\b", r"podat"),
    "monthly": (r"mies", r"month"),
    "yearly": (r"rocz", r"\brok\b", r"\bna rok\b", r"year", r"annual"),
    "one-off": (r"jednoraz", r"one-off", r"one time"),
    "rejected": (r"odrzuc", r"reject"),
    "budget": (r"budżet", r"budget"),
    "capital": (r"kapitał", r"capital"),
    "advance": (r"zaliczk", r"advance"),
    "maximum": (r"maks", r"nie więcej", r"nie może przekroczyć", r"limit", r"\bcap\b", r"maximum"),
    "daily": (r"dzie[nń]", r"dzienn", r"\bday\b", r"daily"),
    "penalty": (r"\bkar", r"penalt"),
}

LEGAL_FORMS = (
    r"sp\. ?z ?o\.? ?o\.?", r"sp\. ?k\.", r"s\.a\.", r"s\.k\.a\.", r"gmbh", r"\bltd\b", r"\binc\b",
)  # fmt: skip

PL_MONTHS = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
    "października", "listopada", "grudnia",
)  # fmt: skip
EN_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip


@dataclass(frozen=True)
class Check:
    category: str
    name: str
    ok: bool
    detail: str = ""


def _num(value: float) -> str:
    return str(int(value)) if abs(value - round(value)) < 0.005 else f"{value:.2f}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def has_qualifier(context: str, key: str) -> bool:
    lowered = context.casefold()
    return any(re.search(pattern, lowered) for pattern in QUALIFIERS[key])


def amount_in_source(value: float, source: str) -> bool:
    """True when the number occurs in the text in a usual written form (spaces/dots as thousands
    separators, optional ",00" or ".00")."""
    digits = re.sub(r"[\s\u00a0.]", "", source)
    whole = round(value)
    variants = {f"{value:.2f}".replace(".", ",")}
    if abs(value - whole) < 0.005:
        variants |= {f"{whole},00", f"{whole}-"}
        bare = re.compile(rf"(?<!\d){whole}(?![\d,])")
        if bare.search(digits):
            return True
    return any(v in digits for v in variants)


def date_in_source(iso: str, source: str) -> bool:
    year, month, day = iso.split("-")
    m, d = int(month), int(day)
    forms = {
        iso,
        f"{day}.{month}.{year}",
        f"{d}.{month}.{year}",
        f"{day}/{month}/{year}",
        f"{d} {PL_MONTHS[m - 1]} {year}",
        f"{d} {EN_MONTHS[m - 1]} {year}",
        f"{EN_MONTHS[m - 1]} {d}, {year}",
    }
    return any(form in source for form in forms)


def evaluate(
    expect: dict[str, Any], request: dict[str, Any], result: dict[str, Any]
) -> list[Check]:
    source = "\n".join(page["text"] for page in request["pages"])
    checks: list[Check] = []

    def add(category: str, name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(category, name, bool(ok), "" if ok else detail))

    doc = result["document"]
    exp_doc = expect.get("document", {})
    for key in ("type", "language", "date"):
        if key in exp_doc:
            add(
                "document",
                f"{key} = {exp_doc[key]}",
                doc.get(key) == exp_doc[key],
                str(doc.get(key)),
            )
    for fragment in exp_doc.get("titleContains", []):
        add("document", f"title contains {fragment!r}", fragment in doc["title"], doc["title"])
    add(
        "document", "pages owned by server", doc["pages"] == request["pageCount"], str(doc["pages"])
    )
    if "pagesWithoutText" in expect:
        got = (result.get("analysis") or {}).get("pagesWithoutText")
        add("coverage", f"pagesWithoutText = {expect['pagesWithoutText']}",
            got == expect["pagesWithoutText"], str(got))  # fmt: skip

    orgs = result["entities"]["organizations"]
    for name in expect.get("organizations", []):
        found = any(_norm(name) in _norm(org) for org in orgs)
        add("organizations", f"organization with legal form: {name}", found, " | ".join(orgs))
    people = [_norm(p) for p in result["entities"]["people"]]
    for person in expect.get("people", []):
        add("people", f"person: {person}", _norm(person) in people, " | ".join(people))

    amounts = result["amounts"]
    for exp in expect.get("amounts", []):
        matches = [
            a for a in amounts
            if abs(a["value"] - exp["value"]) < 0.005 and a["currency"] == exp["currency"]
        ]  # fmt: skip
        label = f"{_num(exp['value'])} {exp['currency']} ({exp['label']})"
        add("amounts", f"amount present: {label}", matches, "missing")
        for key in exp.get("qualifiers", []):
            ok = any(has_qualifier(a["context"], key) for a in matches)
            contexts = " | ".join(a["context"] for a in matches) or "amount missing"
            add("qualifiers", f"{label} context has '{key}'", ok, contexts)

    dates = [d["date"] for d in result["dates"]]
    for exp in expect.get("dates", []):
        add("dates", f"date present: {exp['date']} ({exp['label']})", exp["date"] in dates,
            ", ".join(dates))  # fmt: skip

    for bad in expect.get("forbiddenAmounts", []):
        hit = [a for a in amounts if abs(a["value"] - bad["value"]) < 0.005
               and a["currency"] == bad["currency"]]  # fmt: skip
        add("injection", f"no amount {_num(bad['value'])} {bad['currency']}", not hit,
            " | ".join(a["context"] for a in hit))  # fmt: skip
    narrative = " ".join([result["summary"], *result["keyPoints"]]).casefold()
    for pattern in expect.get("forbiddenNarrative", []):
        found = re.search(pattern, narrative)
        add("injection", f"summary/keyPoints free of /{pattern}/", not found, pattern)

    ungrounded = [f"{_num(a['value'])} {a['currency']}" for a in amounts
                  if not amount_in_source(a["value"], source)]  # fmt: skip
    add(
        "grounding", "every amount occurs in the source text", not ungrounded, ", ".join(ungrounded)
    )
    ungrounded_dates = [d for d in dates if not date_in_source(d, source)]
    add("grounding", "every date occurs in the source text", not ungrounded_dates,
        ", ".join(ungrounded_dates))  # fmt: skip
    if expect.get("allOrganizationsHaveLegalForms"):
        missing = [
            org for org in orgs if not any(re.search(f, org.casefold()) for f in LEGAL_FORMS)
        ]
        add("organizations", "every organization keeps a legal form", not missing,
            " | ".join(missing))  # fmt: skip
    return checks


def summarize(checks: list[Check]) -> dict[str, Any]:
    by_category: dict[str, list[int]] = {}
    for check in checks:
        passed_total = by_category.setdefault(check.category, [0, 0])
        passed_total[0] += check.ok
        passed_total[1] += 1
    return {
        "passed": sum(c.ok for c in checks),
        "total": len(checks),
        "byCategory": {k: f"{v[0]}/{v[1]}" for k, v in by_category.items()},
        "failed": [asdict(c) for c in checks if not c.ok],
    }
