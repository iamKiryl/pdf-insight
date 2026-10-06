# Next implementation: compact TypeScript Worker and bounded model check

2026-10-06, architect decision after b81dc62. User: «давай делать дальше».

## Decision and scope

Proceed with a thin TypeScript Cloudflare Worker for the existing compact path, keeping the Python
implementation as the reference and evaluation tooling. This addresses measured runtime costs;
it is a hypothesis to verify, not a promise that TypeScript will meet 10 ms. Preserve the same
public API, PDF privacy model, Cloudflare Free account, Workers AI binding and frontend. No paid
services, new provider, database, queue or public diagnostic endpoint. Do not move trust-sensitive
validation to the browser. No port of experimental single/chunked modes in this checkpoint.

The deadline recorded in PLAN is today 14:44 Europe/Warsaw. Check time at start; prioritize the
working compact baseline, not extra features. Use the existing manual Claude Opus subscription
workflow. Implement the steps, rather than returning only another plan.

## 1. Establish the parity oracle (no AI)

Create `worker/` for the TS runtime. Before porting, produce local reference fixtures with the
current Python code for both existing evaluation documents and adversarial regressions. Compare
candidate IDs/order, values/currencies/dates, exact contexts, annotation and assembled result.
Use short synthetic fixtures in Git; keep full original recruitment PDFs and captured live text
in ignored local files. Golden outputs must come from reviewed Python behaviour, not the new TS
implementation. Keep independently authored malformed/adversarial cases too.

## 2. Port the compact path

Reuse/extract the existing Zod result contract where appropriate without breaking the frontend.
Port input bounds and page validation, number/date parsing, context selection, request-local
memoization, annotations, compact prompt/schema, selected-ID validation, exact-source people and
organisation rules, marker handling, assembly and coverage metadata. Preserve request ownership
of fileName/pages and explicit long-input rejection. No new extraction heuristics or prompt tuning.

Port transport behaviour: `/api/health`, `/api/analyze`, streaming body bound before parsing,
production fail-closed config, exact origin allowlist, existing IP and global rate-limit bindings,
consistent JSON errors, overall/per-call deadlines, at most one invalid-output correction and
numeric-only usage/error logs. Unsupported modes/models must fail clearly. Provider errors are
not repaired by unlimited retries. Never put AI credentials or a direct provider call in frontend.

Pay attention to Python vs JS differences: Unicode regex/word boundaries, Unicode normalisation,
string offsets (code points vs UTF-16), decimal amounts, date validity, boolean-vs-number coercion,
unknown fields, nulls and enum validation. Preserve source excerpts, not just numerical equality.
Tie tests to contract behaviours; do not generate hundreds of assertions that only mirror code.

## 3. Verify and measure before production

Run parity checks on both documents and existing representative regressions: wrapped money,
headers/footers/table contexts, duplicate facts, wrong names, prompt injection, leaked markers,
unknown candidate IDs, invalid/missing required fields, exactly-one correction, timeout/cancel,
body bounds, CORS and fail-closed rate limiting. Run lint/typecheck/tests/build. Profile the full
TS request path locally in workerd with a fake AI and saved response, separating first/warm runs.
Record that local wall time is not production CPU. Fix actual parity failures; do not weaken the
Python oracle, frontend schema or evaluator. Run relevant existing frontend/Python checks too.

Keep production on its current backend while Codex reviews the migration. Prepare a config to
REPLACE the same Worker only after review, reusing limiter namespace IDs and AI binding; do not
create unrelated infrastructure. Keep the Python fallback deploy command explicit and separate,
so generic instructions cannot accidentally replace the intended runtime. Add TS validation to
existing CI, preserving Python evaluation tests. No public model/runtime switch in this checkpoint.

## 4. Independent, tightly bounded model experiment

First inspect the CURRENT account catalogue and schemas without inference. The official JSON Mode
list names `@cf/meta/llama-3.1-8b-instruct`, but its linked model page returned 404 during architect
review. Do not assume the model still exists based on the list alone. Confirm this exact ID,
context capacity for the entire sample plus output, JSON Schema dialect and Free availability.
Sources checked 2026-10-06:
https://developers.cloudflare.com/workers-ai/features/json-mode/
https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/

If the exact candidate is unavailable/incompatible, record the blocker without calling it or
silently trying other models. This must not block the offline TS migration. Do not re-try the
failed fp8 variant. If available, use the existing Python compact path with a LOCAL model override
to isolate model quality from migration errors. Run sample first; if quality and <30 s pass, run
synthetic offer. Max FOUR actual provider calls including corrections for this new checkpoint,
subject to remaining Free daily quota; keep accounting separate from prior N/N2 calls. Stop on
failure. Keep current evaluator and source review (Claude/AI clearly identified); no selection
of only favourable results. No separate tiny inference probe; the first full sample is the test.
Capture actual observed call counts/errors/tokens; absence of token reporting does not prove zero
billing. No new public sample run yet. Restore local overrides afterwards.

## 5. Deliver reviewable work

Update STATUS, AI_LOG, runtime architecture/setup and evaluation results with actual evidence.
Fix STATUS requirement IDs to match PLAN: F04 strict schema/retry, F05 readable result/JSON,
F07 public demo; the current snapshot mislabeled these. Distinguish code completion from deployed
acceptance. Conventional Commits, clean working tree; preserve prior history. Report:
- parity coverage, deviations and test counts;
- TS local first/warm timing and what is still unmeasured;
- model availability/result and exact provider-call count;
- exact intended deploy command/config and rollback, without executing backend deployment;
- outstanding requirements and time remaining until the recorded deadline.

The already reviewed frontend history fix may be published through existing green CI independently
of backend migration, with no model change or AI calls. Record the deployed frontend revision.
Do not claim the core timeout is fixed by publishing that UI correction.

F08 long documents and F10 OCR remain explicit unfinished goals. Once the baseline meets measured
quality/runtime requirements, return to them. Do not hide failure by canned sample answers,
preloaded successful results, relaxed validation, larger timeout or silent text truncation.
