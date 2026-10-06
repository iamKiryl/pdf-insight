# OCR acceptance and final handoff check — 2026-10-06

Review of c357017: Codex inspected repeated-pass provenance union and correction/cleanup changes;
frontend 136 tests and typecheck passed independently. OCR UI publication is supported by Claude's
real browser report. Model analysis of accepted OCR text is NOT yet verified. No new AI call by
Codex. Approximately one hour remains to the recorded 14:44 Warsaw deadline.

## Last verification task for Claude

1. Prepare a separate OCR-aware acceptance expectation BEFORE inference. Use the page-11 image
   and recorded manual corrections, not an anticipated model response. Check the annex heading,
   amended amounts 12,300 -> 13,100 PLN and context, amended user count 120 -> 135, effective dates
   and signatories against the actual page; preserve history/amendment distinctions rather than
   treating old and amended values as one obligation. Keep prior no-OCR expectations unchanged.
   The OCR case must expect ocrPages [11] and actual remaining missing pages, not the old page-11
   no-text warning. Include absence of false 2/3/5 USD and instruction-injection contamination.
   A correct fact list is required; wording/summary overlap remains editorial, not a new blocker.
2. If Free quota allows, perform ONE public contract analysis after OCR and the documented manual
   corrections, max TWO actual model calls including the allowed correction. The original sample
   is already authorized for this provider in this project. Use an actually fresh browser context
   and verify that rather than assume it; select file through real input. Record OCR/download time,
   human/AI-assisted correction time separately, analysis-to-render, total elapsed, worker CPU,
   version, calls/tokens, output quality and source review labelled Claude/AI. No retries seeking a
   favourable result. The 30-second target does not disappear: report timed components honestly,
   including OCR and user review where applicable, never subtract them silently.
3. Inspect the result, JSON, history reload and OCR warning (no extra calls on reopen). If timeout
   or quota blocks the test, retain failure evidence and explicitly say OCR-to-AI remains unverified.
   If source-quality fails, record the exact issue and do not claim F10 end-to-end accepted. Do not
   ship new unreviewed extraction/model changes to make this test pass before the deadline.
4. Refresh README for the ACTUAL deployed architecture. It currently calls the production backend
   Python/FastAPI/Pydantic in the diagram, shows experimental chunked processing as if deployed,
   and names old TS version d7e5ae75. Change to TS Worker/Zod/compact and current deployed version;
   describe Python as reference/evaluation tooling, chunked as unaccepted experiment. Include OCR
   correction flow and current limits. Verify setup/deploy instructions against actual configs.
   Keep models/private documents/keys out of Git, correct stale public-facing claims, preserve
   the genuine Conventional Commit history and AI_LOG. README screenshots must identify their
   actual origin (history vs fresh result, manual correction vs raw OCR).
5. Write concise docs/HANDOFF.md: demo/repo/CI URLs, exact deployed frontend/backend revisions,
   MUST/SHOULD/COULD checklist, measured successful and failed timings, CPU risk, AI/OCR limits,
   local setup, rollback, availability intent, and remaining F08. Record that runtime/schema
   tests are not proof of semantic accuracy or sustained Free-plan availability. Run the relevant
   required checks and confirm final CI, public files and docs correspond. Commit and push.
   Do not send an application email/form; submission belongs to the user.

Do not start long-document architecture or more provider experiments during this final handoff
checkpoint. F08 remains an unmet requested SHOULD, not cancelled or silently counted complete.
Current free deployment may still exceed CPU limits; no paid upgrade or reliability guarantee.
If time expires, deliver the actual supported state and unfinished list rather than declaring all
criteria fulfilled. Return concise facts the user can use for their submission decision.
