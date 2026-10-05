# Live-quality evaluation (evaluator v3)

Offline checks for real model outputs. Nothing here calls the model or another judge. `run_live.py`
sends one request to a **locally running** Worker (`uv run pywrangler dev`), which may call the
model up to twice (first call + one corrective retry); `rescore.py` re-evaluates saved responses.

## What is checked automatically (`checks.py`, `sources.py`)

- Result schema (the API's Pydantic model) before anything else; HTTP errors fail immediately.
- Server-owned metadata and coverage: `fileName`, `pages`, `analysis.pagesWithoutText`/`complete`.
- Document type, language, main date, title fragment; organisations with exact legal names.
- Every expected amount: present with the same value **and currency**; the stated qualifiers
  (net/gross/VAT, period, status) on the **same entry**; no contradicting qualifier on that entry
  (e.g. both "netto" and "brutto", or "miesięcznie" for a yearly fee) and no negation.
- Every expected date: present, and its context names the expected event (all event groups).
- Injection markers; grounding: every amount occurs in the source as a whole number token with
  the same currency (adjacent marker or page-level "Waluta: PLN"), every date occurs in the source.

Numbers are parsed as bounded tokens (184 500,00 / 184.500,00 / 184,500.00 / 12.34 / plain
integers); percentages and zero-padded identifiers are not amounts. Dates: ISO, dd.mm.yyyy,
"12 marca 2026", "March 12, 2026".

These checks establish presence, association and grounding — **not semantic entailment**.

## What needs a human (never counted as passed automatically)

`summary_factual`, `key_points_factual`, `contexts_meaning`, `language_fidelity`. The report
includes an evidence table for them (numbers/dates in the summary and key points with grounding
flags, all contexts with detected qualifiers, characters outside the Polish alphabet). A manual
review file applies only to the exact result it names:

```json
{"resultSha256": "<from the report>", "reviewer": "name", "date": "YYYY-MM-DD",
 "dimensions": {"summary_factual": {"verdict": "pass", "note": "..."}, "...": {}}}
```

## Status

- `failed` — HTTP/connection error, invalid schema, a failed automatic check, measured latency
  ≥ 30 s, an ungrounded case, or a manual dimension judged `fail`.
- `needs_manual_review` — nothing failed, but a manual dimension is unreviewed or latency was not
  measured.
- `accepted` — everything above passed. A local latency < 30 s still does not certify deployed
  upload-to-result latency.

## Cases

- `cases/synthetic_offer_pl.json` — synthetic Polish offer (in the repository); every expected fact
  cites a page and an exact snippet. `synthetic_offer_pl.reference.json` is a hand-written factual
  answer (passes every automatic check, still needs manual review).
- `fixtures/adversarial_offer_result.json` — labelled schema-valid nonsense; must never be accepted.
- `cases/sample_contract.json` — expected facts for the recruitment sample with page + snippet; its
  text stays in the git-ignored `.local/`. Nothing is expected from the image-only page 11.

## Commands

```bash
cd backend
# one live request (recording mode always exits 0)
uv run python -m evaluation.run_live --case synthetic_offer_pl --label <label> \
  --worker-log ../.local/live/worker.log
# acceptance mode: exit 0 accepted, 1 failed, 2 needs_manual_review
uv run python -m evaluation.run_live --case synthetic_offer_pl --label <label> --check \
  --manual-review <review.json>
# re-evaluate saved responses offline (manifest lists response paths, HTTP status, latency)
uv run python -m evaluation.rescore ../.local/live/rescore-manifest.json
```
