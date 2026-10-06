# Public demo review and stability checkpoint — 2026-10-06

Reviewed 08ff026. Codex opened the public Pages URL and confirmed the upload screen, four steps,
privacy notice and empty history render. Independently ran all 102 frontend tests, typecheck and
lint successfully. Read the history implementation and tests; the main reopen/delete/save flow is
reasonable. CI success is reported in the deployment report; Codex's separate web fetch of the CI
run was unavailable. No new AI requests were made during this review.

## Release verdict

Publication and F-09 are delivered; final acceptance is NOT complete. The saved public run L
summary records HTTP 504, one model call timed out at 40 s, Worker wall 40,005 ms and CPU 303 ms.
These are separate issues. A smaller/faster model might reduce wall time, but does not establish
CPU compatibility. Conversely, optimizing Python will not necessarily resolve inference latency.

Cloudflare's current limits documentation states 10 ms CPU per HTTP request on Free, excludes
network waiting from CPU, and permits occasional overruns before enforcing sustained overuse:
https://developers.cloudflare.com/workers/platform/limits/#cpu-time
Therefore a response without error 1102 is not proof that 303 ms is safe on Free. The exact CPU
hotspot and repeatability are not yet known. Do not label it purely cold-start overhead without
measurement. Previous good runs remain valid observations; they do not cancel public run L.

## Small history issue to fix

`browserStorage()` tests availability by writing a probe. If localStorage is already full, that
write throws and the function returns null: readable saved analyses, deletion and quota eviction
then become inaccessible. The lower-level quota tests inject a fake directly and bypass this real
browser entry point. Keep readable storage available on QuotaExceededError; distinguish that from
SecurityError. Add a regression through the default browserStorage/useHistory path with a failed
probe and an existing valid entry. Verify reopening/clearing and a new analysis remain usable.
Do not make all read/write failures look identical or claim deletion succeeded if it failed.

## Next Claude task — stabilize the baseline before F-08/F-10

Use the existing manual Opus subscription workflow. No paid infrastructure or API credits for
implementation. Work on local commits; do not deploy a speculative rewrite or switch the public
model before the checks below. Preserve the public site while investigating. Read the current
Warsaw time and deadline from the brief; prioritize stability, not new UI or extra features.

1. Fix the history edge case above and run the relevant tests plus frontend checks. Maintain
   truthful state when storage operations fail. No unrelated refactoring.
2. Profile CPU without AI calls first. Replay the saved sample request and saved valid compact
   response through the existing pipeline with a fake AI in LOCAL test/profiling tooling. Separate
   parsing/Pydantic, candidate extraction and annotation, output validation/normalization, and
   entrypoint/ASGI overhead. Include first/warm invocations; distinguish CPython, local workerd
   and Cloudflare measurements. Use measured hotspots to make a focused optimization, preserving
   all evidence, bounds, injection defenses, source-name checks and regression tests. Do not
   publish a diagnostic endpoint or a fake-result path in production. Health/invalid requests
   can help estimate transport overhead, but cannot prove CPU for real analysis. A CPU profile
   with mocked AI also does not measure binding/timeout overhead; document that limitation.
3. In a local override only, benchmark ONE smaller Cloudflare-hosted model using the same compact
   contract. Candidate: `@cf/meta/llama-3.1-8b-instruct-fp8` (official card lists 32k context and
   response_format). Confirm current availability, JSON-schema support, context and Free quota
   before calling; if incompatible, report it rather than silently trying a list of models.
   Official card: https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct-fp8/
   This is a scoped model experiment, not an assertion that 8B is faster or good enough in Polish.
   Start with the sample; only if quality and <30 s pass, run the synthetic offer. At most FOUR
   provider calls total for these two analyses, including corrections. No changes to evaluator
   thresholds, no dropping required facts, no growing timeouts to conceal the latency failure.
   Use the same source-based AI review and label it Claude/AI. Stop on a factual or timing failure.
4. Record a concrete decision based on CPU and model evidence. If focused Python optimizations
   are adequate locally and both model trials pass, prepare the exact candidate production config,
   changed UI model disclosure, and offline regression evidence for Codex review. Keep the deployed
   model unchanged during this checkpoint. If CPU remains substantially above 10 ms in representative
   workerd measurements, report which costs dominate and the smallest viable free alternative
   (e.g. a thin TypeScript Worker with equivalent server-side validation), with migration scope;
   do not start a second backend implementation yet. Faster inference alone is not a CPU fix.
5. Update current STATUS and README so 'implemented' is distinct from 'accepted on public demo'.
   Correct outdated current-looking sections in DEPLOYMENT (production 429 was independently
   observed by Codex, F-09 and Pages now exist); retain clearly labelled historical evidence.
   Record every provider call, elapsed time, CPU evidence, quality result and unknown in AI_LOG /
   LIVE_AI_RESULTS. Logical Conventional Commits; no raw request text or credentials in logs.

Report commits, tests, CPU breakdown, model verdict and the exact proposed next deployment or
remaining architectural blocker. No further public sample retries in this checkpoint, no quota
reset assumptions, no paid upgrade. F-08 long documents and F-10 OCR remain queued and incomplete;
this review does not cancel those goals.

## Follow-up review of 4cfb355 — 2026-10-06

Codex reviewed the four implementation commits after this task. History quota handling and failed
write/delete state are improved; 107 frontend tests, typecheck and lint passed independently.
Ruff lint/format passed; backend pytest: 435 passed, five fixture setup errors because this review
sandbox denies binding a localhost socket (`test_run_live_check.py`), not failed application
assertions. Saved candidate output before/after memoisation is byte-identical for the sample.

Saved local workerd profiling reports pipeline iteration estimates 41.6 → 23.5 ms and extraction
38.1 → 20.3 ms. These are client wall-time estimates of repeated work, not production CPU metrics.
Saved deployed M health/invalid-body requests report 16–49 ms CPU. The optimization is promising,
but the evidence does not resolve Free compatibility or justify a public model switch.

This checkpoint is incomplete in the repository: 8B has been added to MODEL_PROFILES, but no 8B
live result/evaluation was found and STATUS/AI_LOG still describe the previous checkpoint. Finish
steps 3–5 above. If a live experiment already happened outside these files, recover its evidence
and record it; DO NOT duplicate calls. If it never ran, use only the original remaining four-call
budget after checking current quota. Report a blocked experiment explicitly rather than implying
it passed. Keep current deployment unchanged. Do not repeat completed profiling/history work.
