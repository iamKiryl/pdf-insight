# Chunked extraction (F-08) — design note

Status: implemented as an **opt-in experiment** (`AI_MODE=chunked`); the default stays the
single-call mode (`AI_MODE=single`). Verified only with scripted provider responses — no live
model call has used this path yet, so quality, latency and quota below are design estimates.

## Flow

```
request (≤ 64 000 chars of text)
  ├─ build_chunks: readable pages in order → ≤ 8 chunks of ≤ 10 000 chars
  │     pages > 10 000 chars split at paragraph/line/space, ≤ 300 chars repeated context
  ├─ overview call  ── full text, or digest = start of EVERY page if text > 30 000 chars
  ├─ chunk call × N ── typed facts: amounts (value, currency, basis, period, status, context,
  │                    page, exact excerpt), dated events (date, event, page, excerpt),
  │                    organisations, people, keywords
  │   (≤ 2 calls in flight, overview queued first, one overall deadline, ≤ 1 retry in total)
  ├─ grounding (inside each chunk call's validation): every fact's excerpt must occur in that
  │             chunk's text and contain the value/date; the amount's currency and stated
  │             qualifiers must be supported at that occurrence; otherwise the chunk output is
  │             invalid → the request's single retry → failure (nothing is dropped silently)
  └─ merge → public AnalysisResult (same contract as single mode)
```

Code: `backend/src/pdf_insight/chunking.py`, `chunk_prompt.py`, `merge.py`, `chunked.py`.

## Chunking rules

- Only pages with extractable text are sent; `analysis.pagesWithoutText` keeps the scan warning.
- Phase 1 packs whole pages. Phase 2 (only if phase 1 needs more than 8 chunks) fills chunks and
  splits pages where needed, closing a chunk only with < 1 000 chars of space left. This proves
  that every text up to 64 000 chars fits in 8 chunks (module docstring; property-tested on 40
  random documents). Larger texts get an explicit `DOCUMENT_TOO_LONG`; nothing is truncated.
- The overlap (≤ 300 chars, starting at a word boundary) lets a fact cut by a split be read whole
  from the continuation; a fact seen twice through the overlap collapses in the merge.

## Grounding rules (revised after docs/REVIEW_CHUNKING.md)

- The excerpt is located inside the chunk's own segments and mapped to exact raw offsets in the
  page (not the first occurrence on the page).
- Amounts: the number token must lie inside the cited occurrence; its currency comes from the
  marker next to it or the page's "Waluta:"/"Currency:" line and must equal the claimed currency.
  A short quote that omits the currency does not license any currency.
- Each claimed basis/period/status other than unspecified/other/current must be named in the same
  sentence or table row as the value (bounded to 200 characters each side). The sentence window is
  a conservative heuristic (abbreviations such as "sp. z o.o." can shorten it), so legitimate facts
  may be rejected; rejection is preferred to inventing a qualifier.
- Any unsupported fact makes the chunk output invalid. Grounding runs inside the call's validation,
  so it shares the request's single correction retry; an unresolved rejection fails the request
  with AI_INVALID_OUTPUT. Text-layer coverage (`analysis.pagesWithoutText`) is unaffected.

## Merge rules

- Never add up amounts; never merge across currency, net/gross/VAT basis, period or status.
- Two amount entries collapse only when value, currency, basis, period, status and normalised
  context are identical **and** they cite the very same source occurrence (same page and offsets,
  e.g. text seen twice through chunk overlap). Overlapping or shared quotes alone never establish
  identity — ambiguous facts are kept, not guessed together.
- Dated events collapse only for the same date, the same normalised event and the same source
  occurrence; different events on one date — even citing one sentence — stay separate.
- Organisations: case-insensitive de-duplication; the only alias rule drops a name when another
  listed name is exactly that name plus a legal form ("Kwadrat Software" / "Kwadrat Software
  S.A."). Shared prefixes ("Alfa" / "Alfa Logistics") stay distinct.
- Supported structured qualifiers missing from the free-text context are appended in the document
  language (Polish/English labels only, e.g. "(netto, miesięcznie)"). Because the evaluator's
  keyword checks then pass, context meaning still needs manual review.
- Chunk outputs are data. They are never sent to another model call; injection text inside a
  chunk stays inside that chunk's `<document>` block.

## Document-level fields and schedule

Chosen option: **one overview call in parallel with the chunk calls** (queued first). It sees the
full text when it fits in 30 000 chars, otherwise a deterministic digest made of the beginning of
every readable page (budget water-filled so short pages stay whole). Amounts and dates in the
result always come from the full-text chunk calls.

Rejected alternatives: a summary call after extraction (adds a full sequential call to the
latency) and per-chunk summaries merged by another call (also sequential). The parallel overview
re-reads the document, so it costs input tokens instead of latency. Concurrency does not
guarantee any latency target.

## Limits, failure handling and call budget

| Limit | Value | Where |
|---|---|---|
| request text envelope | 64 000 chars (single mode: 48 000, explicit 413 above) | `contracts/limits.json` |
| chunk size / overlap / max chunks | 10 000 / 300 / 8 | `chunking.py` |
| concurrent model calls | 2 | `chunked.py` |
| overall AI budget / per call / browser | 55 s / min(40 s, time left) / 65 s | `limits.json` |
| corrective retries | 1 per request (not per chunk) | `chunked.py` |

- A call is not dispatched once the budget is spent. Timeouts, quota and provider errors are never
  retried. Any failing call cancels the others and fails the request — an incomplete extraction is
  never returned as a result (scan warnings and processing failures stay separate).
- Calls per analysis: `chunks + 1` (overview), plus at most 1 retry → **2 to 10 calls**.

## Estimated cost and latency (not measured)

Neurons from catalog prices for `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (26 668 per M input,
204 805 per M output tokens) and the single-call checkpoint's ~2.45 prompt chars per token:

| Case | Calls | Input tokens | Output tokens | Neurons |
|---|---|---|---|---|
| sample contract, single mode (measured) | 1 | 9 359 | 763 | ≈ 406 |
| sample contract, chunked (3 chunks + overview) | 4 | ≈ 21 000 | ≈ 1 800–2 700 (guess) | ≈ 930–1 110 |
| worst case (8 full chunks + digest overview + 1 retry incl. its previous answer, outputs at max_tokens) | 10 | ≈ 59 000 | ≈ 19 500 | ≈ 5 600 |

At the free allocation of 10 000 neurons/day this means roughly 9–10 chunked analyses of the
sample per day, and fewer than 2 worst-case analyses.

Latency risk: the sample needs 4 calls, i.e. two rounds at concurrency 2. Every 70B call measured
so far took 30–35 s, so with the 55 s overall budget the second round would get ≤ 25 s per call and
the request would likely end in `AI_TIMEOUT` — unless smaller chunk outputs are faster, which is
unmeasured. The live comparison must decide between keeping the budget, raising it for this mode,
or a different model; concurrency is fixed at 2 for this experiment.

CPU/memory: chunking, grounding and merging are linear in the text size (≤ 64 000 chars) plus
regex parsing of short excerpts; Workers Free CPU (10 ms per request) is unmeasured for either
mode and is not claimed.

## Not done

Live quality/latency/quota comparison against the single-call baseline; F-09 history; F-10 OCR;
deployment.
