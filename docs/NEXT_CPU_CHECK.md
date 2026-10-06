# Review of deployed TS runtime and final CPU check — 2026-10-06

Codex reviewed d2d92fe and saved P artifacts: evaluator 71/71, upload-to-render 26,531 ms,
coverage warning, export/reopen evidence and numeric tail. No new code since the accepted TS
review; no repeated tests or inference by Codex. Public baseline succeeded on this run.

37 ms CPU remains unresolved. Comparing it with Python's 303 ms is not a controlled 8x benchmark:
the Python request timed out, the TS request completed, and isolate conditions were not matched.
The direction of improvement is supported also by health/invalid-request measurements. Do not
attribute all remaining CPU to cold-start without evidence, or guarantee 14-day reliability.

## Next Claude task (bounded investigation, then report)

1. Keep the working TS deployment and model unchanged initially. Profile LOCAL workerd with the
   existing fake-AI replay and actual CPU profiler (DevTools/CDP if available). Separate first and
   warm requests, JSON/input validation, candidate extraction/annotation, response parsing,
   name/entity checks, Zod output validation and serialization/logging. Include full run-P-shaped
   provider response with usage as well as its payload. No production fake endpoint, no private
   document in Git. Use local stage timing only as local evidence; Cloudflare timer precision does
   not provide per-function CPU measurements. Do not spin/sleep to simulate inference.
2. If a clear hotspot has a small behaviour-preserving fix, implement it and run all parity cases,
   worker tests/typecheck and applicable CI. Profile before/after with identical inputs. Do not
   strip validation, alter the prompt/schema, move trusted work into the browser, or add caches
   retaining user documents across requests. Dynamic regex compilation, repeated text scans and
   duplicate schema/serialization work are hypotheses to examine, not presumed causes.
3. Only if there is a demonstrated local improvement, deploy the focused change to the same
   Worker, recording the current TS dd6a5db2 version as the rollback target. Otherwise keep it.
   Under remaining Free quota, perform ONE further public sample analysis (new checkpoint budget:
   max TWO provider calls including correction). Capture actual worker CPU and wall time, output
   quality, exact version and upload-to-render. If unchanged runtime is used, this is a second
   observation; do not call it guaranteed warm unless isolate identity is established. Stop after
   that analysis regardless of outcome. Preserve failed and successful results alike.
4. Report whether the observed analysis CPU is <=10 ms; no inference from health or lack of 1102.
   If still over, document the operational risk and the measured hotspot, rather than opening an
   unbounded rewrite or buying infrastructure. Do not consume remaining time with repeated random
   model trials. Correct the package description still calling the TS Worker 'not deployed'.
5. Update STATUS/AI_LOG/LIVE_AI_RESULTS with evidence and logical commits. Record time remaining
   to 14:44 Warsaw. Keep F08 and F10 explicitly open; do not equate a warning with their completion.

Limit this investigation to about 30 minutes of active work; if tools or measurement are blocked,
record that and return a concrete result rather than spending the deadline on diagnostics. This
is a checkpoint timebox, not a request to terminate an in-flight inference or conceal failures.
Next architectural decision will balance remaining CPU risk, long-document/OCR scope and deadline.
