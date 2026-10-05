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
  ├─ grounding: keep a fact only if its excerpt occurs on a page of that chunk and contains the
  │             value/date; page taken from where the excerpt is found; others dropped + counted
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

## Merge rules

- Never add up amounts; never merge across currency, net/gross/VAT basis, period or status.
- Two amount entries collapse only when value, currency, basis, period and status match **and**
  their excerpts overlap on the same page (the same text seen twice). Equal values elsewhere stay
  separate — ambiguous facts are kept, not guessed together.
- Dated events collapse only for the same date with overlapping excerpts on one page or the same
  normalised event text; different events on one date stay separate.
- Organisations: case-insensitive de-duplication; a name that is a word-prefix of a longer listed
  name (typically missing the legal form) is dropped in favour of the longer one.
- Structured qualifiers missing from the free-text context are appended in the document language
  (Polish/English labels only, e.g. "(netto, miesięcznie)"). Note: the evaluator's keyword
  qualifier checks will therefore pass whenever the model's structured fields are set — those
  fields still need manual review.
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
