# Last bounded model comparison on compact — 2026-10-06

User asked what to do next. At 12:24 Warsaw the recorded deadline is 14:44. Prioritize baseline
latency; end CPU micro-optimisation and unavailable-Llama experiments. No paid upgrade/provider.

## Rationale

70B occupied 30.2 of run Q's 30.7 seconds. Gemma 4 was previously tried only with the old full
extraction schema: it generated 2048 tokens and truncated. It has NOT been evaluated with the
current compact schema (candidate IDs rather than repeated amount/date contexts). This is a
specific changed-workload hypothesis, not evidence Gemma will be faster or pass quality. Prior
truncation cause (repetition vs reasoning) remains unknown; capture enough local evidence to
resolve it if reproduced. Official model card exists:
https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/

## Claude implementation task

Use manual Opus subscription, existing repo, Free account. Keep current deployment intact during
comparison. No F08/OCR work until this bounded decision returns; those goals remain open.

1. Confirm exact `@cf/google/gemma-4-26b-a4b-it` schema and account availability without inference.
   Use the existing Python model adapter (OpenAI-style json_schema and enable_thinking=false)
   with AI_MODE=compact as a LOCAL override. Keep compact-v4 content/schema/limits unchanged.
   Verify emitted request options locally, and source-grounding/evaluator setup before calling.
2. Check available Free quota conservatively; unknown usage stays unknown. Run sample once, max
   two provider calls including correction. Capture usage, finish reason, response shape and
   truncated-output diagnostics in ignored local artifacts, never public logs or Git. Apply the
   same 71 checks and source review identified as Claude/AI. Stop this model on error, timeout,
   factual failure or >=30 s total local time. A comfortable margin below30 is preferable, but
   do not invent a new mandatory quality threshold. No dropping required facts or increasing
   timeouts/output cap to force a pass. No repeated calls seeking a favourable result.
3. Only if sample passes, run synthetic offer once (max two calls including correction), with
   unchanged evaluation. Total comparison ceiling FOUR calls, including corrections. Restore
   local overrides afterwards regardless of outcome. If either fails, record it and STOP model
   experimentation; keep 70B production and report actual limitations for delivery planning.
4. If BOTH pass, port only the already-used model request/response adapter to TS. Preserve default
   70B until tests pass. Test both response dialects, malformed output, truncation/correction and
   no-third-call behaviour; run parity, worker/TypeScript checks and CI. Update the frontend AI
   disclosure to the actual selected model and model-specific docs. Do not leak internal reasoning
   into result/history. Preserve the compact result contract and all grounding checks.
5. After success, deploy this narrowly scoped change to the same TS Worker and frontend through
   CI, recording exact current TS version for rollback. Run ONE public sample analysis (max TWO
   calls including correction) with numeric tail and the current evaluator/source review. Record
   CPU as well as latency: changing a model does not prove CPU <=10 ms. Total checkpoint maximum
   SIX provider calls, only when quota permits. Roll back the model/config/disclosure together on
   functional or quality regression; report an isolated timing miss honestly without extra runs.
6. Update STATUS, LIVE_AI_RESULTS, DEPLOYMENT and AI_LOG, logical commits, exact public revision
   and current time. Timebox the comparison and adapter work to ~40 minutes; preserve working
   production if the candidate cannot be finished and checked in that window. No partial deploy.

CPU 37–39 ms remains a separate Free-hosting risk even if this model succeeds. No promise of
14-day reliability, no paid purchase, no concealed limits. F08/F10 are not cancelled or counted
complete; after this checkpoint choose remaining scope against actual time and measured results.
