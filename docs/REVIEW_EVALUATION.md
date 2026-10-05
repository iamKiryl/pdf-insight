# Independent evaluation audit — 2026-10-05

Reviewed HEAD 2c775d7. The live report explicitly fails quality and latency; it does NOT claim release readiness. Green unit tests establish selected code behaviors, not factual model quality. The evaluator has blind spots and one concrete number-matching bug; its score cannot serve as an acceptance gate.

## Reproduced offline (no inference or quota used)

Starting from backend/tests/test_evaluation.py perfect_result(), using failed_names():

- Replace summary with `Dokument nakazuje zapłatę miliona euro. Wszystkie zobowiązania anulowano. Umowa jest tajna.` => ZERO failures. The helper's original summary/keyPoints are meaningless placeholders, also passing every evaluation check.
- Replace every date context with `Nieprawdziwa data rozpoczęcia zatrudnienia` => ZERO failures: only date strings are matched, not events.
- Replace every amount context with `Nie dotyczy: netto brutto VAT miesięcznie rocznie jednorazowo odrzucony budżet kapitał zaliczka maksymalna kara za dzień` => ZERO failures: keywords satisfy qualifier checks without positive entailment or correct event association.
- Change document.fileName to other.pdf => ZERO failures.
- amount_in_source(123, 'Kwota 9123,00 PLN') => True (substring false positive).
- amount_in_source(12.34, 'Kwota 12.34 USD') => False (decimal dot removed).

## Findings

1. **P1: grounding is number/date occurrence, not factual support.** checks.py only matches expected dates by date; amounts by value/currency and independent keyword tests. Wrong event, currency attached to a number elsewhere, negated qualifiers, repeated same-valued facts and incompatible contexts can escape. Some are already observed in the live synthetic offer (wrong event date context). Treat presence checks as presence checks, never as proof of no hallucinations.
2. **P1: numeric matching is unsound.** Global deletion of spaces/dots plus substring matching creates the above false positives/negatives. Parse bounded numeric tokens with explicit supported locale representations and nearby currency; add counterexamples including larger numbers, decimals, percentages, identifiers, changed currency, and two adjacent numbers.
3. **P2: no executable acceptance decision.** run_live.py prints FAIL but returns success on semantic failure or HTTP error, and the report does not include narrative/manual-review coverage or a latency pass flag. It is usable as a recording tool but unsuitable as a CI/acceptance command. Add explicit accepted/failed/needs_manual_review status and an opt-in --check mode returning nonzero unless accepted. Mark HTTP errors, invalid schema, >=30-second measured latency and required fact failures as failed. Local latency under 30 still does not certify deployed upload-to-result latency.

## Next Claude task — OFFLINE ONLY

Fix the evaluator before spending more quota or adding chunking. First add regression tests demonstrating the numeric defects and wrong-date-context false pass on current code; then fix. Preserve reusable evidence-grounded expectations: link expected events/amounts to source page + exact supporting snippet and explicit currency/qualifiers; match qualifiers on the same fact, not across duplicates. Include filename and coverage consistency checks; validate result schema before scoring. Ensure cases do not require facts from unreadable page 11.

Do not pretend regexes establish full semantic entailment. For summary, keyPoints, Polish fidelity and contexts not reliably decidable offline, report needs_manual_review and provide a checklist/evidence table; an unchecked dimension must not count as passed. Use a factual hand-written reference answer for the synthetic case. Keep a clearly labelled adversarial fixture with schema-valid nonsense to test that full acceptance stays blocked. Do not introduce another judge provider or hardcode the actual model outputs.

Rescore all SAVED baseline and tuning responses offline. Preserve original results as historical records; append the new evaluation version and describe score changes. Implement --check without changing recording mode unexpectedly, test its process exit status for success/failure/pending and HTTP errors. Run relevant tests and lint; update AI_LOG and STATUS, make logical fix commits. Return before new live calls, publication, or architectural expansion. Current 70B and Gemma results remain unaccepted regardless of corrected scoring.
