# Optional browser OCR checkpoint — 2026-10-06

Decision after b39774d: Gemma compact failed the offer's rejected-variant fact. Three failed
assertions refer to that same omission; it is a real completeness issue under our existing plan.
Keep 70B and the deployed TS backend. Stop model experiments and CPU rewrites for this checkpoint.
Public latency and 37–39 ms CPU remain unresolved risks, not cancelled requirements.

Implement F10 as an OPTIONAL browser feature because page 11 of the sample contains a scanned
annex. The user wanted additional requirements too. This does not complete F08 or fix baseline
latency. Timebox ~45 minutes; retain a reviewed working baseline if the feature cannot be tested.
Check current Warsaw time and the recorded 14:44 deadline. Use manual Claude Opus subscription.

## Implementation

- Use existing pdf.js to render only selected pages without a text layer, then Tesseract.js in a
  browser Web Worker, Polish + English. Tesseract.js does not directly read PDFs. Official docs:
  https://github.com/naptha/tesseract.js . Check the installed version's API. Pin dependencies and
  asset versions; lazy-load OCR only after user action. No remote OCR service or AI model call.
- Offer an explicit Polish 'recognize scanned pages' action after text extraction, including when
  every page is scanned. Keep the normal text-only/partial-analysis path available unchanged.
  Show progress, cancellation and useful failure feedback. Bound pages/pixels/time and process
  sequentially with one worker; release canvases, PDF tasks and OCR worker on cancel/reset/unmount.
  Prevent stale OCR results from attaching to a subsequently chosen file. Document actual bounds.
- Display OCR text for review with a warning that amounts/names/dates can be misread. Let the user
  explicitly choose to use the recognized text before AI analysis. Preserve original page numbers
  and normal text-layer pages; do not duplicate or silently replace them. Recompute missing pages
  from accepted text; unrecovered pages stay flagged. Enforce existing total character limits after
  OCR; no truncation. No automatic model request when OCR finishes.
- Preserve OCR provenance/warning on result, JSON/history as appropriate with compatible optional
  metadata and tests for older entries. Do not claim OCR text is ground truth or that every scan
  is readable. The model must know which provided text was OCR-derived. Keep strict schema checking
  and shared contracts aligned if metadata changes; do not alter extraction/evaluator thresholds.
- PDF/page images remain in browser memory; only the text the user chooses to analyze goes to the
  existing backend. Serve pinned worker/WASM/language files from Pages where practical; if language
  assets come from a third-party static host, disclose that download and verify images/text are
  never sent there. No private PDFs or page screenshots in Git. Check Pages base-path loading.

## Verification and delivery

- Real OCR locally: sample page 11, plus a synthetic image-only page with known Polish text,
  names, amounts and date. Inspect the rendered source and compare the transcription; record
  actual recognition errors, duration and asset-download behaviour. Do not substitute a mocked
  OCR success for this check. Keep sample source evidence ignored; synthetic fixtures can be Git.
- Tests: opt-in flow, success, cancellation/reset races, unreadable page, load failure, size/char
  bounds, retained partial warning and OCR provenance on reopen. Existing text-only path must not
  load OCR assets or change its payload inadvertently. Run frontend checks, applicable shared
  contract/backend/worker tests and Pages build. No Workers AI calls in this checkpoint.
- Prepare code and updated docs for Codex review BEFORE publishing the feature. Commit logically;
  report actual tests, OCR text fidelity, build impact, limitations, current time, and whether the
  implementation is ready or blocked. Keep current public deployment untouched until review.

F08 long documents remains next in the unfinished list. Do not mark the whole project complete.
If OCR cannot be made safe and reviewable within the timebox, preserve the feature work separately
and report the concrete blocker; do not deploy an unfinished feature to meet a checkbox.
