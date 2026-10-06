"""Evaluator v3: fact-level automatic checks, explicit manual-review dimensions and a status.

Automatic checks are deliberately narrow and conservative. They establish *presence and
association* of expected facts (the right amount entry carries the stated qualifiers and no
contradicting ones; the right date entry names the expected event) and *grounding* (every amount
and date in the result occurs in the source as a bounded token with the same currency). They do
NOT establish semantic entailment.

Source-quote contexts (compact mode) mark the selected occurrence as »value«; a true sentence may
state net, VAT and gross values together. For such a context, qualifiers are associated with the
marked occurrence only: the text between the neighbouring value tokens (money or dates) or
sentence ends around the marker, excluding a bracketed column header/heading, and the marked text
must parse to the entry's own value. Contexts without exactly one marker keep the blanket rule
(any contradicting qualifier anywhere in the context fails). A date-event subcheck that a case
marks ``"eventReview": "manual"`` (e.g. an issue-date header such as "Warszawa, dnia …" that
does not name its role) is reported as a manual subcheck when it does not match automatically:
neither passed nor failed, it keeps the status at needs_manual_review until a contexts_meaning
review of this exact result passes (or fails it). A missing date still fails.

Summary, key points, the full meaning of contexts and language fidelity are reported as
``needs_manual_review`` with an evidence table; an unchecked dimension is never counted as passed.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from evaluation.sources import amounts_on_page, as_decimal, dates_on_page
from pdf_insight.contract import AnalysisResult

EVALUATOR_VERSION = "eval-v4-2026-10-06"
LATENCY_LIMIT_MS = 30_000  # the brief's target; a local measurement never certifies deployment

# Qualifier vocabulary (Polish + English stems).
QUALIFIERS: dict[str, tuple[str, ...]] = {
    "net": (r"\bnetto\b", r"\bnet\b"),
    "gross": (r"\bbrutto\b", r"\bgross\b"),
    "vat": (r"\bvat\b", r"podat"),
    "monthly": (r"mies", r"month"),
    "yearly": (r"rocz", r"\brok\b", r"/rok", r"year", r"annual"),
    "one-off": (r"jednoraz", r"one-off", r"one time"),
    "daily": (r"każdy dzień", r"dzienn", r"\bper day\b", r"daily", r"za dzień"),
    "rejected": (r"odrzuc", r"reject"),
    "budget": (r"budżet", r"budget"),
    "capital": (r"kapitał", r"capital"),
    "advance": (r"zaliczk", r"advance"),
    "maximum": (
        r"maks",
        r"nie więcej",
        r"nie może przekroczyć",
        r"\blimit",
        r"\bcap\b",
        r"maximum",
    ),
    "penalty": (r"\bkar[ay]?\b", r"\bkara", r"penalt"),
}
# Mutually exclusive qualifier groups: an entry may carry at most one member, and none other than
# the expected one. This blocks keyword soup ("netto brutto miesięcznie rocznie ...").
EXCLUSIVE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"net", "gross"}),
    frozenset({"monthly", "yearly", "one-off", "daily"}),
)
NEGATIONS = (r"nie dotyczy", r"\bn/a\b", r"not applicable", r"brak danych")  # not bare "na" (pl)
LEGAL_FORMS = (
    r"sp\. ?z ?o\.? ?o\.?", r"sp\. ?k\.", r"s\.a\.", r"s\.k\.a\.", r"gmbh", r"\bltd\b", r"\binc\b",
)  # fmt: skip
MANUAL_DIMENSIONS = (
    "summary_factual",  # every sentence supported by the document, nothing important misstated
    "key_points_factual",
    "contexts_meaning",  # each amount/date context describes the right fact, not just keywords
    "language_fidelity",  # correct document-language spelling/diacritics, no corrupted characters
)
_POLISH_LETTERS = set("aąbcćdeęfghijklłmnńoóprsśtuwyzźżqvx")
EXIT_CODES = {"accepted": 0, "failed": 1, "needs_manual_review": 2}


@dataclass(frozen=True)
class Check:
    category: str
    name: str
    ok: bool
    detail: str = ""
    manual: bool = False  # a subcheck that needs the contexts_meaning review when it does not pass


_MARKED = re.compile(r"»([^»«]+)«")
_BRACKETED_PREFIX = re.compile(r"^s\. \d+: (?:\[[^\]]*\] )?")
_SENTENCE_BREAK = re.compile(r"[.!?;]\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])")
_TWO_DECIMALS = re.compile(r"[.,]\d{2}$")


def _value_spans(text: str) -> list[tuple[int, int]]:
    spans = [(t.start, t.end) for t in amounts_on_page(0, text)
             if t.adjacent_currency or _TWO_DECIMALS.search(t.text)]  # fmt: skip
    return spans + [(m.start(), m.end()) for m in _DATE_TOKEN.finditer(text)]


_DATE_TOKEN = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+[a-ząćęłńóśźż]+\s+\d{4}", re.IGNORECASE
)


def occurrence_segment(context: str) -> str | None:
    """The text associated with the single »marked« occurrence (None without exactly one
    marker): from the previous value token or sentence end to the next one, header excluded."""
    marks = list(_MARKED.finditer(context))
    if len(marks) != 1 or context.count("»") != 1 or context.count("«") != 1:
        return None
    mark = marks[0]
    prefix = _BRACKETED_PREFIX.match(context)
    body_start = prefix.end() if prefix else 0
    left = context[body_start : mark.start()]
    right = context[mark.end() :]
    cut = max([end for _, end in _value_spans(left)]
              + [m.end() for m in _SENTENCE_BREAK.finditer(left)] + [0])  # fmt: skip
    stops = [start for start, _ in _value_spans(right)]
    stops += [m.start() + 1 for m in _SENTENCE_BREAK.finditer(right)]
    return left[cut:] + mark.group(1) + right[: min(stops, default=len(right))]


def association_text(context: str) -> str:
    segment = occurrence_segment(context)
    return context if segment is None else segment


def marked_value_matches(context: str, value: float, currency: str) -> bool:
    """True without a marker; with one, the marked text must be this value (and currency, when
    the marked text names one; a page-level currency is checked by grounding)."""
    mark = _MARKED.search(context)
    if mark is None:
        return True
    target = as_decimal(value)
    return any(as_decimal(t.value) == target and t.currency in (None, currency)
               for t in amounts_on_page(0, mark.group(1)))  # fmt: skip


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def qualifiers_in(context: str) -> set[str]:
    lowered = context.casefold()
    return {key for key, pats in QUALIFIERS.items() if any(re.search(p, lowered) for p in pats)}


def has_qualifier(context: str, key: str) -> bool:
    return key in qualifiers_in(context)


def conflicts(context: str, expected: set[str], entry: dict | None = None) -> list[str]:
    problems = []
    if entry is not None and not marked_value_matches(context, entry["value"], entry["currency"]):
        problems.append("marked occurrence is a different value")
    context = association_text(context)
    found = qualifiers_in(context)
    for group in EXCLUSIVE_GROUPS:
        present = found & group
        if len(present) > 1 or (present and expected & group and present - expected):
            problems.append("/".join(sorted(present)))
    if any(re.search(p, context.casefold()) for p in NEGATIONS):
        problems.append("negation")
    return problems


def source_index(request: dict[str, Any]) -> tuple[list[Any], set[str]]:
    tokens, dates = [], set()
    for page in request["pages"]:
        tokens += amounts_on_page(page["page"], page["text"])
        dates |= dates_on_page(page["text"])
    return tokens, dates


def validate_case(case: dict[str, Any], request: dict[str, Any]) -> list[str]:
    """Check the case itself: every expected fact cites a readable page and an exact snippet that
    contains the value (with its currency on that page) or the date."""
    problems = []
    unreadable = set(request["pagesWithoutText"])
    texts = {p["page"]: p["text"] for p in request["pages"]}
    for kind in ("amounts", "dates"):
        for fact in case["expect"].get(kind, []):
            label = f"{kind}:{fact.get('label')}"
            page, evidence = fact.get("page"), fact.get("evidence", "")
            if page in unreadable or page not in texts:
                problems.append(f"{label}: page {page} is not readable text")
            elif not evidence or _norm(evidence) not in _norm(texts[page]):
                problems.append(f"{label}: evidence not found on page {page}")
            elif kind == "amounts":
                target = as_decimal(fact["value"])
                in_evidence = any(as_decimal(t.value) == target
                                  for t in amounts_on_page(page, evidence))  # fmt: skip
                with_currency = any(
                    as_decimal(t.value) == target and t.currency == fact["currency"]
                    for t in amounts_on_page(page, texts[page])
                )
                if not (in_evidence and with_currency):
                    problems.append(f"{label}: evidence lacks {fact['value']} {fact['currency']}")
            elif fact["date"] not in dates_on_page(evidence):
                problems.append(f"{label}: evidence lacks {fact['date']}")
    return problems


def schema_errors(result: Any) -> list[str]:
    try:
        AnalysisResult.model_validate(result)
    except ValidationError as exc:
        return [
            f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False)
        ]
    return []


def _best_entry(entries: list[dict], expected: set[str]) -> dict | None:
    """Among entries with the expected value and currency, pick the one that carries most of the
    expected qualifiers with fewest conflicts — qualifiers are judged on ONE entry, never pooled
    across duplicates."""

    def score(entry: dict) -> tuple[int, int]:
        found = qualifiers_in(association_text(entry["context"]))
        return (len(found & expected), -len(conflicts(entry["context"], expected, entry)))

    return max(entries, key=score) if entries else None


def evaluate(
    expect: dict[str, Any], request: dict[str, Any], result: dict[str, Any]
) -> list[Check]:
    """Automatic, fact-level checks. ``result`` must already be schema-valid."""
    checks: list[Check] = []

    def add(category: str, name: str, ok: bool, detail: str = "", manual: bool = False) -> None:
        checks.append(Check(category, name, bool(ok), "" if ok else detail, manual and not ok))

    tokens, source_dates = source_index(request)
    doc = result["document"]
    analysis = result.get("analysis") or {}

    add("metadata", "fileName = request fileName", doc["fileName"] == request["fileName"].strip(),
        doc["fileName"])  # fmt: skip
    add("metadata", "pages = request pageCount", doc["pages"] == request["pageCount"],
        str(doc["pages"]))  # fmt: skip
    add("coverage", "analysis.pagesWithoutText = request pagesWithoutText",
        analysis.get("pagesWithoutText") == request["pagesWithoutText"],
        str(analysis.get("pagesWithoutText")))  # fmt: skip
    add("coverage", "analysis.complete consistent with readable pages",
        analysis.get("complete") is (not request["pagesWithoutText"]),
        str(analysis.get("complete")))  # fmt: skip

    exp_doc = expect.get("document", {})
    for key in ("type", "language", "date"):
        if key in exp_doc:
            add("document", f"{key} = {exp_doc[key]}", doc.get(key) == exp_doc[key],
                str(doc.get(key)))  # fmt: skip
    for fragment in exp_doc.get("titleContains", []):
        add("document", f"title contains {fragment!r}", fragment in doc["title"], doc["title"])

    orgs = result["entities"]["organizations"]
    for name in expect.get("organizations", []):
        add("organizations", f"organization with legal form: {name}",
            any(_norm(name) == _norm(org) for org in orgs), " | ".join(orgs))  # fmt: skip
    if expect.get("allOrganizationsHaveLegalForms"):
        missing = [o for o in orgs if not any(re.search(f, o.casefold()) for f in LEGAL_FORMS)]
        add("organizations", "every organization keeps a legal form", not missing,
            " | ".join(missing))  # fmt: skip
    people = {_norm(p) for p in result["entities"]["people"]}
    for person in expect.get("people", []):
        add("people", f"person: {person}", _norm(person) in people, " | ".join(sorted(people)))

    for fact in expect.get("amounts", []):
        target = as_decimal(fact["value"])
        label = f"{fact['value']} {fact['currency']} ({fact['label']}, p.{fact['page']})"
        entries = [
            a for a in result["amounts"]
            if as_decimal(a["value"]) == target and a["currency"] == fact["currency"]
        ]  # fmt: skip
        add("amounts", f"amount present: {label}", entries, "missing")
        expected = set(fact.get("qualifiers", []))
        best = _best_entry(entries, expected)
        context = best["context"] if best else "amount missing"
        for key in sorted(expected):
            add("qualifiers", f"{label} same entry has '{key}'",
                best is not None and has_qualifier(association_text(context), key),
                context)  # fmt: skip
        if best is not None:
            bad = conflicts(context, expected, best)
            add("qualifiers", f"{label} entry has no contradicting qualifier", not bad,
                f"{', '.join(bad)} in: {context}")  # fmt: skip

    for fact in expect.get("dates", []):
        label = f"{fact['date']} ({fact['label']}, p.{fact['page']})"
        entries = [d for d in result["dates"] if d["date"] == fact["date"]]
        add("dates", f"date present: {label}", entries,
            ", ".join(d["date"] for d in result["dates"]))  # fmt: skip
        groups = fact.get("event", [])  # every group must match; any stem within a group
        if groups:
            ok = any(
                all(any(re.search(p, e["context"].casefold()) for p in group) for group in groups)
                for e in entries
            )
            shown = " & ".join("/" + "|".join(group) + "/" for group in groups)
            contexts = " | ".join(e["context"] for e in entries) or "date missing"
            manual = bool(entries) and fact.get("eventReview") == "manual"
            add("dates", f"{label} context names the event {shown}", ok, contexts, manual)

    for bad in expect.get("forbiddenAmounts", []):
        hit = [a for a in result["amounts"] if as_decimal(a["value"]) == as_decimal(bad["value"])
               and a["currency"] == bad["currency"]]  # fmt: skip
        add("injection", f"no amount {bad['value']} {bad['currency']}", not hit,
            " | ".join(a["context"] for a in hit))  # fmt: skip
    narrative = " ".join([result["summary"], *result["keyPoints"]]).casefold()
    for pattern in expect.get("forbiddenNarrative", []):
        add("injection", f"summary/keyPoints free of /{pattern}/",
            not re.search(pattern, narrative), pattern)  # fmt: skip

    ungrounded = [
        f"{a['value']} {a['currency']}" for a in result["amounts"]
        if not any(as_decimal(t.value) == as_decimal(a["value"]) and t.currency == a["currency"]
                   for t in tokens)
    ]  # fmt: skip
    add("grounding", "every amount occurs in the source with the same currency", not ungrounded,
        ", ".join(ungrounded))  # fmt: skip
    ungrounded_dates = [d["date"] for d in result["dates"] if d["date"] not in source_dates]
    if doc.get("date") and doc["date"] not in source_dates:
        ungrounded_dates.append(f"document.date {doc['date']}")
    add("grounding", "every date occurs in the source", not ungrounded_dates,
        ", ".join(ungrounded_dates))  # fmt: skip
    return checks


def manual_evidence(request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Evidence for the human reviewer. It helps the review; it does not replace it."""
    tokens, source_dates = source_index(request)

    def numbers_in(text: str) -> list[dict[str, Any]]:
        return [
            {"text": t.text,
             "inSource": any(as_decimal(s.value) == as_decimal(t.value) for s in tokens)}
            for t in amounts_on_page(0, text)
        ]  # fmt: skip

    fields = [
        result["summary"], *result["keyPoints"],
        *(a["context"] for a in result["amounts"]), *(d["context"] for d in result["dates"]),
    ]  # fmt: skip
    unusual = sorted({ch for f in fields for ch in f
                      if ch.isalpha() and ch.lower() not in _POLISH_LETTERS})  # fmt: skip
    return {
        "summary": {"text": result["summary"], "numbers": numbers_in(result["summary"]),
                    "dates": sorted(dates_on_page(result["summary"]))},
        "keyPoints": [{"text": k, "numbers": numbers_in(k)} for k in result["keyPoints"]],
        "amountContexts": [
            {"value": a["value"], "currency": a["currency"], "context": a["context"],
             "associatedText": association_text(a["context"]),
             "qualifiersDetected": sorted(qualifiers_in(association_text(a["context"])))}
            for a in result["amounts"]
        ],
        "dateContexts": [{"date": d["date"], "context": d["context"],
                          "inSource": d["date"] in source_dates} for d in result["dates"]],
        "charactersOutsidePolishAlphabet":
            unusual if result["document"]["language"] == "pl" else "not checked",
    }  # fmt: skip


def result_digest(result: Any) -> str:
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def assess(
    case: dict[str, Any],
    request: dict[str, Any],
    result: Any,
    *,
    http_status: int,
    latency_ms: int | None,
    manual_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``failed``: HTTP error, invalid schema, measured latency ≥ 30 s, a failed automatic check, an
    ungrounded case, or a manual dimension judged "fail". ``needs_manual_review``: nothing failed
    but something is unchecked (a manual dimension, or latency not measured). ``accepted``: every
    automatic check passed, latency measured < 30 s and every manual dimension reviewed "pass"
    for exactly this result (matched by SHA-256)."""
    report: dict[str, Any] = {
        "evaluatorVersion": EVALUATOR_VERSION,
        "case": case["id"],
        "httpStatus": http_status,
        "latencyMs": latency_ms,
        "caseProblems": validate_case(case, request),
    }
    failures: list[str] = []
    pending: list[str] = []
    if report["caseProblems"]:
        failures.append("case expectations are not grounded in the source")
    if http_status != 200 or result is None:
        failures.append(f"HTTP {http_status}")
        report.update(status="failed", reasons=failures, automatic=None, manual=None)
        return report
    errors = schema_errors(result)
    if errors:
        failures.append("result does not match the API schema")
        report.update(status="failed", reasons=failures, schemaErrors=errors, automatic=None,
                      manual=None)  # fmt: skip
        return report

    checks = evaluate(case["expect"], request, result)
    if latency_ms is None:
        pending.append("latency not measured")
    else:
        checks.append(Check("latency", f"measured latency < {LATENCY_LIMIT_MS} ms (local only)",
                            latency_ms < LATENCY_LIMIT_MS, f"{latency_ms} ms"))  # fmt: skip
    failed = [c for c in checks if not c.ok and not c.manual]
    subchecks = [c for c in checks if c.manual]
    checks = [c for c in checks if not c.manual]
    if failed:
        failures.append(f"{len(failed)} automatic check(s) failed")

    digest = result_digest(result)
    verdicts: dict[str, str] = {}
    if manual_review and manual_review.get("resultSha256") == digest:
        verdicts = {k: v.get("verdict", "") for k, v in manual_review.get("dimensions", {}).items()}
    manual = {dim: verdicts.get(dim, "unreviewed") for dim in MANUAL_DIMENSIONS}
    failures += [f"manual review failed: {d}" for d, v in manual.items() if v == "fail"]
    pending += [f"unreviewed: {d}" for d, v in manual.items() if v not in ("pass", "fail")]
    if manual["contexts_meaning"] == "unreviewed":
        pending += [f"manual subcheck (contexts_meaning): {c.name}" for c in subchecks]

    by_category: dict[str, list[int]] = {}
    for check in checks:
        counts = by_category.setdefault(check.category, [0, 0])
        counts[0] += check.ok
        counts[1] += 1
    report["automatic"] = {
        "passed": sum(c.ok for c in checks),
        "total": len(checks),
        "byCategory": {k: f"{v[0]}/{v[1]}" for k, v in by_category.items()},
        "failed": [asdict(c) for c in failed],
        "manualSubchecks": [asdict(c) for c in subchecks],
    }
    report["manual"] = {"resultSha256": digest, "dimensions": manual,
                        "evidence": manual_evidence(request, result)}  # fmt: skip
    status = "failed" if failures else "needs_manual_review" if pending else "accepted"
    report.update(status=status, reasons=failures + pending)
    return report
