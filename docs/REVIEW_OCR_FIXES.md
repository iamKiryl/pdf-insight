# OCR review: two fixes before publishing — 2026-10-06

Reviewed b4c46d8. Independently ran frontend 127 tests and typecheck (pass). Inspected OCR engine,
flow/review UI, request/result provenance and contract changes. No AI call made by Codex.

## Findings

1. `applyOcr` replaces `ocrPages` with newly recognised pages. Reproduction: a 3-page document
   has scans 2 and 3; first pass recognises only page 2, accept it; second pass recognises page 3.
   Page 2's text stays but provenance becomes [3] instead of [2,3]. The repeated-OCR button is
   available for remaining missing pages. This silently drops a meaningful warning and source tag.
2. Real page-11 OCR turns section symbols into $ and creates false USD candidates. The current
   review UI is read-only: the user can accept incorrect text or discard the whole OCR, but cannot
   correct it. Add a general correction step; DO NOT silently replace all '$' with '§' or invent a
   rule deleting small USD amounts. Real dollar amounts must survive. Missing headings and o/0
   errors require the same source-comparison workflow.
3. Resource caveat: `openPdfWithPdfJs` exposes destroy only after task.promise resolves; cancelled
   initialization is released only if that promise eventually resolves. A render that resolves
   after bounded() has timed out lacks its image.release call. Documentation's 'at once' is too
   broad. Address late render cleanup with a regression; document remaining initialization limits
   honestly rather than claiming an unresolved promise has been cancelled.

## Claude task (target ~25 minutes, then review-ready/deploy as below)

- Preserve the union of prior and newly accepted OCR page numbers, sorted/unique and limited to
  pages with text. Add the 2-pass regression through applyOcr AND the flow/request. Empty/failed
  second pass must not erase earlier provenance; normal text pages cannot become OCR pages.
- Make each OCR result editable in a labelled textarea, retaining its original recognized text
  locally for reset/comparison. User can correct '$' to '§', '0.0.' to 'o.o.' and restore a heading
  from the PDF they inspect. A local page preview or a clear way to compare with the original is
  needed. Never automate those replacements. Recompute readiness, letter-based missing pages,
  limits and counts on edits; no truncation and no automatic AI call. Permit correction of an
  initially unreadable page too. Preserve OCR provenance even after user correction; avoid claiming
  machine confidence describes the edited text. Discard restores pre-OCR data.
- Handle/release late render results and test the cancellation/timeout race. Keep lazy loading,
  no third-party data transmission, original PDF in memory only and existing normal analysis.
- Real local verification: page 11, source-check all reconstructed text and demonstrate correcting
  the three '$' section markers. Offline candidate extraction on that edited text must remove the
  false USD candidates and retain correct PLN amounts/dates. Also test a genuine '$ 5' monetary
  statement remains unchanged when user does not edit it. Record machine errors and user edits
  separately; don't report corrected text as perfect automatic recognition.
- Run relevant tests, full frontend checks/build, shared-schema/Python/TS parity and CI. If these
  fixes and real OCR checks pass, deploy the compatible Worker FIRST and Pages SECOND using the
  already-reviewed config/model. Record version IDs and rollback targets. Verify static OCR asset
  loading from the public base path and UI flow without AI. Keep raw sample images/text ignored.
  Roll back frontend first if rolling back incompatible backend schema.
- Do not run an AI analysis in this checkpoint. End-to-end model handling of OCR remains explicitly
  unverified; F10 is locally source-checked OCR with user correction, not automatically verified
  fact extraction. Keep speed/CPU and F08 open. Update OCR/STATUS/AI_LOG and actual deployment docs;
  report commits, test counts, public versions and current time before the 14:44 Warsaw deadline.

If a fix cannot be verified in the remaining time, keep the feature unpublished and report the
specific blocker; preserve the existing functioning public text-only path.
