# Codex chunking review — 2026-10-05

## Re-review of 06f389b: findings closed for bounded live comparison

Codex reviewed the changes and independently repeated the original reproductions: both 100 PLN obligations and both same-date events survive merge; the unsupported USD/yearly claim is rejected; absent evidence raises InvalidModelOutput instead of disappearing. Grounding now runs inside the shared correction budget. Ruff lint/format passed; 331 backend tests passed (unchanged local-socket CLI test file excluded in this run). Frontend unchanged since the prior successful check. No AI calls used. These findings are closed; this is permission to evaluate the experimental mode, not a claim of semantic correctness or production readiness.

Next Claude checkpoint: run ONE analysis of the sample contract with AI_MODE=chunked, after checking available free quota, using the existing input and default 55-second overall deadline. It should plan 3 chunks + overview, maximum FIVE started provider calls including the one shared corrective retry. If planning exceeds this cap, stop before calling. Count actual starts, including cancelled calls; do not increase concurrency, token cap or deadlines to force success. Do not repeat automatically or change model/prompt mid-experiment. Keep the committed default single; local override only, restore afterward. No publication or paid changes.

Record per-call label, timing, completion/finish reason where available, known token usage and safe validation field paths/reasons (no source text in normal logs). Preserve request/result under ignored .local/. Run evaluator v3 on any result, then actually review summary, key points, contexts and Polish fidelity against source; record specific errors, do not simply mark all manual dimensions pass. Report failure precisely if timeout/invalid evidence/output happens, including which phase and how many calls completed. Update LIVE_AI_RESULTS, STATUS and AI_LOG with a focused commit, then return for architectural decision. A failed trial is useful evidence; do not conceal it by weakening grounding or dropping facts.

After this trial we must decide the final approach from observed quality, latency and quota; do not continue speculative chunking expansion. History, OCR and deployment remain unfinished.

Reviewed 99a2f20. Working tree clean before review. Independent checks: backend Ruff lint/format passed, 311 pytest tests passed excluding tests/test_run_live_check.py (socket-based CLI tests unchanged, previously reviewed); frontend lint/typecheck, 81 tests and build passed. No provider calls. Experimental opt-in status and unchanged single-call default are correct. Chunk mode is NOT yet accepted for live testing.

## P1 — merging drops distinct obligations/events

In merge.py, merge_amounts deduplicates on value/currency/basis/period/status and overlapping evidence, ignoring obligation meaning. merge_dates uses overlap OR equal event text. A single supporting sentence can cover multiple events. Reproduction through real ground_chunk -> merge, using one page:

`Serwis kosztuje 100 PLN netto miesięcznie. Hosting kosztuje 100 PLN netto miesięcznie. Podpisanie i zapłata: 12.03.2026.`

Return two amount entries with contexts Serwis and Hosting, both 100 PLN net/monthly, each citing the full text; two date entries for 2026-03-12 with events Podpisanie and Zapłata, same citation. Both survive grounding, but merge returns ONE amount and ONE date (duplicate_amounts=1, duplicate_dates=1). Both pairs must survive. Existing tests cover differing periods/currencies or non-overlapping citations and miss this case. _locate also uses full-page find(), so repeated identical snippets at different offsets can be assigned the first occurrence even for later segments.

Fix conservatively: overlapping evidence is insufficient to establish identity. Preserve ambiguous entries; exact event/obligation agreement plus a genuinely identical source occurrence can support deduplication. Use segment offsets to locate actual occurrences. merge_organizations currently removes Alfa when Alfa Logistics exists merely by prefix; preserve distinct names, restricting any alias rule to a verified legal-form-only extension or dropping that heuristic.

## P1 — evidence does not support currency/qualifiers that are added as facts

For the same source page, return amount(value=100, currency=USD, basis=net, period=yearly, context=Serwis, evidence=`Serwis kosztuje 100`). ground_chunk accepts the quote without currency because matching tokens with currency None pass. merge emits `100 USD`, context `Serwis (netto, rocznie)`, although the source explicitly says PLN/monthly. This is a reproducible fabricated fact introduced through the new grounding/label pipeline.

Resolve currency and qualifier evidence from the specific source occurrence, bounded surrounding text or an explicit applicable currency declaration. An omitted currency in a short quote must not license any model-supplied currency. Do not append an unsupported enum as factual prose. If support is ambiguous, fail the chunk's validation (using the existing one shared correction budget) rather than invent a value. Do not attempt an unbounded NLP subsystem: conservative rejection is sufficient for this fix. Preserve legitimate explicit evidence and table/declaration tests.

## Silent evidence rejection must be visible

Returning an unsupported amount 999 PLN with a nonexistent citation drops it, then merge returns empty amounts with analysis.complete=true for an all-text PDF. Today droppedFacts exists only in server logs. Keep text-layer coverage separate from extraction validation: do not silently present dropped candidate facts as a clean successful analysis. Preferred simple behavior for this stage: evidence rejection invalidates that chunk before success and uses the existing global retry budget; unresolved rejection fails the request. If a partial-result alternative is chosen, it requires explicit API/UI/download warnings and tests, not merely a changed log.

## Next Claude task

Fix ONLY these defects, adding reproductions as regression tests first. Keep AI_MODE=single as default; no live calls, publishing, extra models, OCR or other feature expansion. Integrate evidence validation inside the per-chunk retry boundary without increasing the global retry allowance or losing cancellation/deadline behavior. Test distinct events/obligations within overlapping quotes, repeated equal snippets across split-page segments, distinct organization prefixes, short quotes hiding contradictory currency/period, all facts rejected, correction success and exhausted global correction budget. Run checks, update AI_LOG/STATUS, make focused fix commits and return for review.
