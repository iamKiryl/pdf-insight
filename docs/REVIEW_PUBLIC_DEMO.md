# Backend deployment review and public demo task — 2026-10-06

Reviewed HEAD 3c76fa8 against 66f8de5. Changes promote the already reviewed compact implementation
in deployment configuration; no new analyzer implementation. Reported runs I/J/K pass the current
evaluator and Claude's source review. K reports 25.3 s upload-to-render through the deployed backend
and local frontend. This is one successful measurement, not a latency guarantee.

Codex independently checked the deployed Worker on 2026-10-06 around 06:59 UTC:
- GET /api/health: 200, production, compact, AI and rate-limiter bindings present.
- Pages-origin preflight: 204 with the expected allow-origin; foreign origin: 403.
- Invalid JSON-object POSTs: 400; subsequent requests returned 429 RATE_LIMITED. The application
  checks rate limits before parsing the body, so these checks made zero model calls. Initial short
  bursts did not immediately return 429; this does not establish an exact five-request hard cap.
  Counters are eventually consistent and per location, not an account-wide quota guarantee.
- Python urllib initially received Cloudflare 1010 before the app; curl successfully reached it.

No new implementation blocker identified. CPU consumption still unknown. The deployed model-call
count cannot be established from latency alone: replace the claimed/inferred exact checkpoint count
with two observed local analyses plus one deployed analysis whose provider-call count is unobserved,
unless actual numeric server logs establish it. Preserve historical observations.

## Next task for Claude (manual subscription workflow)

Work in this repository. Complete this checkpoint without changing model/provider or paying for
services. Do not send recruitment emails or forms. Preserve the existing logical Conventional
Commit history. Do not use API credits for implementation.

1. Implement F-09 local browser history, consistent with the existing dark/lime design. Keep at
   most 10 validated analysis results and enforce a serialized size bound. Store results and file
   metadata only, never original PDFs or extracted source text. Explain that history is stored on
   this device and may contain document data. Provide reopen, delete-one and clear-all controls.
   Reopening must use the existing result view/JSON export without another AI request. Handle
   unavailable/quota-exceeded storage and malformed/old entries without breaking current analysis.
   Validate stored data with the existing schema. Add meaningful tests for persistence, reopening,
   corruption, bounds and clearing. Keep basic PDF processing usable without storage.
2. Run existing frontend lint, formatting, typecheck, Vitest and Pages-path build; run backend
   checks in the release CI. Fix real failures without weakening assertions. Verify history and
   result display at 360 px. Update screenshots if materially changed.
3. Inspect the authenticated GitHub account and intended repository before publication. Publish
   this assignment as public `pdf-insight` under the user's account if it does not exist; do not
   overwrite or repurpose an unrelated repository. Inspect tracked files AND history for secrets,
   private mail, credentials and unintended local documents before pushing. Keep `.local`,
   `.dev.vars`, OAuth credentials and raw live artifacts excluded. The brief/test PDF are not to
   be newly published. Preserve history rather than squashing to one initial commit.
4. Set the repository variable VITE_API_URL to the deployed Worker URL, enable GitHub Pages via
   Actions, and run the existing workflow_dispatch with deploy=true. Inspect every required job
   and fix actual CI failures. Verify action versions exist if a resolution failure occurs; don't
   bypass CI. Use the real repository base path. If account differs from iamkiryl, align the exact
   Pages browser origin in Worker CORS; remove any temporary localhost origin afterwards.
5. Open the public Pages URL as an unauthenticated visitor. Check initial state, pdf.js worker
   loading, mobile layout, error handling and history with existing local data. Perform at most
   ONE real sample analysis (at most TWO provider calls including correction), only if remaining
   Free quota allows. Use the current evaluator and source review, identify Claude as AI reviewer,
   measure upload-to-render, inspect page-11 warning, JSON export and history reopen without an
   extra request. Record failures honestly; no retry loop to obtain a favourable time.
6. Inspect available Cloudflare CPU metrics/logs for existing successful requests, without exposing
   document text or credentials and without new AI calls just for metrics. Record observed CPU
   values/aggregation and resource-limit errors if present; otherwise keep CPU compatibility
   unverified. Actual quota usage is unknown unless observed. Do not infer provider-call count
   from elapsed time. Check numeric model-call logs if available.
7. Refresh README with actual public demo/repo URLs, screenshot, setup, limitations and the intended
   14-day availability period (future uptime cannot be certified now). Make STATUS start with a
   current snapshot; move contradictory old 'nothing deployed' claims into clearly dated history.
   Update DEPLOYMENT and AI_LOG with actual prompts, commits, CI results and evidence. Commit any
   final docs and ensure the public source matches the deployed application revision.

Deliver the demo URL, repository URL, CI run URL, commit hashes, test counts, live result and remaining
limitations. Stop only the dependent step if access/ownership/quota blocks it and report the exact
blocker. No paid upgrade, no new infrastructure, no weakening validation to obtain a pass.

F-08 (long-document processing) and F-10 (OCR) remain separate unfinished work after this checkpoint.
Do not present compact's >30,000-character rejection or scan warning as completing them. The task
is not fully complete while those requested enhancements remain unresolved; first secure the public
baseline and history, then plan the remaining work using the actual time/quota available.
