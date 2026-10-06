# Review 76ab90d — 2026-10-06

Codex reviewed desktop-idle and mobile-ready screenshots: styling matches the supplied brief (dark surfaces, lime accents, strong headings, numbered steps); no visible layout blocker in those screenshots. This is screenshot inspection, not independent browser accessibility testing. Independently passed frontend lint/format/typecheck, 90 tests and Pages-base build; backend Ruff lint/format and 416 tests excluding the unchanged local-socket CLI test file. Working tree clean before review. No AI inference in this review.

## Correct the acceptance interpretation

The brief requires 3–7 factual key points. It does not prohibit overlap with the summary. The architect's earlier "no summary repetition" instruction was an editorial preference, not a MUST requirement. In saved run G, the three points express different supported facts and may overlap the summary; repetition alone should be a nonblocking editorial issue. Preserve the historical failed verdict and add this explicit reinterpretation, do not rewrite history or globally relax factual checks. Do not claim every point is literally identical: the first also omits the signing date found in the summary.

## Real remaining issue: person name fidelity

Run G returns `Marek Zielińskiego`, a hybrid of grammatical forms. Source contains `Marka Zielińskiego` in the introduction and `Marek Zieliński` at signature. Do not hardcode these names. Make exact source-name copying explicit and validate person names against source with whitespace/Unicode normalization; preserve attested inflection, do not guess nominative morphology. Unknown/mixed names should trigger the existing single correction attempt rather than silent dropping or fuzzy rewriting. A valid exactly attested alternative is acceptable. Add tests for inflected names, mixed forms and unrelated people; inspect missing named people as a completeness limitation separately. Keep all error/retry/deadline limits intact.

## Next Claude task

1. Apply the focused name-fidelity fix and tests. Keep the new UI. No new architecture/model experiments. Update STATUS's stale release-gate section: clearly distinguish old single-mode results from current compact measurements and list actual open issues.
2. Run the previously withheld synthetic offer in compact mode (max 2 provider calls including correction) and evaluate schema, factual quality, names, contexts, injection and latency. Do not fail merely because summary and key points overlap; actual false facts or duplicated points within the keyPoints list remain issues. Record reviewer identity accurately.
3. If successful, repeat the sample once (max 2 calls) to verify the name correction and prevent regressions. Total checkpoint <=4 calls, within confirmed free access; stop on substantive failure without repeated tuning. Actual usage unknown must stay labelled unknown. No publication in this checkpoint.
4. If both pass, prepare compact as the proposed release mode and explicit backend deployment instructions/configuration for live CPU, CORS, rate-limit and upload-to-render checks; return for final publication step. Do not claim deployed <30s or Free CPU compliance from local measurements. Preserve baseline/experimental code clearly labelled; do not count unvalidated chunking as F08. F09 history and F10 OCR remain open and must not vanish from the checklist. Update AI_LOG and use focused commits.
