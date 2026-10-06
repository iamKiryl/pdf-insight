# Current snapshot — 2026-10-06, 12:20 Warsaw (CPU check)

Deadline recorded in docs/PLAN.md: 2026-10-06 14:44 Warsaw (≈ 2 h 24 min left).

| Item | State |
|---|---|
| Public demo | https://iamkiryl.github.io/pdf-insight/ — frontend from `54515a5` |
| Backend | TypeScript Worker `pdf-insight-api`, version `d7e5ae75-a043-45c7-8f7f-2ecac09e9d74` (app code `17593aa`); rollback targets: TS `dd6a5db2-5c7d-4b1f-b037-b8608459087e`, Python `a4695cc8-ac6c-47a9-9253-6facf931c2b9` |
| Public sample analyses on TS | P (`dd6a5db2`): 26.5 s, CPU 37 ms, accepted. **Q (`d7e5ae75`): 30.7 s upload-to-render — over the 30 s target**, CPU 39 ms, 70/71 (only latency failed), AI review pass |
| Analysis CPU vs Free 10 ms | **not met**: 37 ms and 39 ms observed (both the first analysis after a deploy); non-AI requests 0–5 ms; no resource-limit errors |
| Checks | worker 169 tests (89 parity + 66 phrase-equivalence + 14 behaviour), backend 444, frontend 107 |

Requirements (IDs as in docs/PLAN.md):

| ID | Requirement | Code complete | Accepted on the public demo |
|---|---|---|---|
| F-01 | Drag & drop / chooser, PDF ≤ 10 MB | yes | yes |
| F-02 | Text layer extraction, pages without text | yes | yes |
| F-03 | 3–5 sentence factual summary | yes | content yes in P and Q (AI review); timing passed in P, failed in Q |
| F-04 | Strict schema, one retry on invalid output | yes | yes (valid first call in P and Q; correction path tested offline) |
| F-05 | Readable result, JSON view and download | yes | yes |
| F-06 | Empty, loading, error and retry states | yes | yes |
| F-07 | Public GitHub Pages demo | yes | **not reliably**: 1 of 2 public TS analyses under 30 s (26.5 s, 30.7 s); model latency dominates (25.8 / 30.2 s per call); CPU above the documented Free limit |
| F-08 | Long documents (SHOULD) | **no** | no |
| F-09 | Local history (SHOULD) | yes | yes |
| F-10 | OCR (COULD) | **no** | no |

## CPU check (docs/NEXT_CPU_CHECK.md)

CDP CPU profiles of local workerd (wrangler dev inspector; fake AI returning a run-P-shaped
provider response with usage; fresh isolate for each "first" request; 50 µs sampling):

| Local workerd, sample request | first request, non-idle CPU | GC in first request | warm, per request |
|---|---|---|---|
| before (`dd6a5db2` code), run 1 / 2 | 23.6 / 20.2 ms | 24.4 / 0.7 ms (first value an outlier) | 4.80 / 4.97 ms |
| after (`17593aa`), run 1 / 2 | 15.6 / 15.0 ms | 0.8 / 0.8 ms | 4.93 / 4.93 ms |

Hotspots: cold request — `unattestedPeople` (a lookbehind `\p{L}` regex compiled per name and run
over all pages, ≈ 3.6 ms) and duplicate character counting; warm — spread over date/number
parsing, `pySplit`, `countLetters` (no single hotspot). Fix `17593aa`: literal whole-phrase search
with the same boundary rule (66 equivalence cases) and one count per request; parity unchanged.

Production after deploying the fix (run Q, first analysis after deploy like P): **39 ms CPU**
(P: 37 ms). The local cold-start gain is not visible in one production sample; the remaining
production CPU is not explained by the measured local cost (≈ 15–25 ms cold, ≈ 5 ms warm) — the
difference may come from isolate start, JIT state, binding (de)serialisation of the 25 KB prompt
and response, or machine speed; not established. The fix is behaviour-identical and stays
deployed. Operational risk: each analysis exceeds the documented 10 ms; Cloudflare tolerates
occasional overruns, sustained overuse may be enforced. No further optimisation or rewrite was
started (timebox).

Measurement correction: runs P and Q were driven through a headless Chrome instance left over
from run L (same scratch profile, no logins) instead of a fresh profile — still an anonymous
visitor, but run P's history entry was present in Q (history count 2). Timing and server
measurements are unaffected. The leftover processes were closed after Q.

## TS deployment checkpoint (docs/REVIEW_TS_DEPLOY.md)

Before mutation: deployed version `a4695cc8-ac6c-47a9-9253-6facf931c2b9` recorded; worker code
unchanged since review; 103 tests and typecheck re-run. Deployed from `worker/wrangler.jsonc`.
Transport without AI: health 200 (`production`, AI and limiters bound), Pages preflight 204 with
the origin header, foreign origin 403, localhost 403, two full-size invalid requests 400; every
event carried `scriptVersion dd6a5db2…`, analyze events `"runtime":"ts"`, no exceptions.
One public analysis via headless Chrome (fresh profile, real file input) — see run P above and
docs/LIVE_AI_RESULTS.md. One success is not a reliability guarantee; the 70B latency risk remains.

## Free runtime checkpoint (docs/NEXT_FREE_RUNTIME.md)

**Parity oracle:** `backend/tools/parity_fixtures.py` (Python) → `worker/test/parity/` — 23
synthetic/adversarial cases incl. 19 selection scenarios, the synthetic offer (oracle + all
candidates), the exact prompt and schema; the 12-page sample with run J's selection only in
`.local/parity/` (git-ignored). Python freshness test in the backend job.

**TS Worker:** compact path ported 1:1 (Unicode `\w`/`\b`/whitespace emulated, Python
`finditer(pos, endpos)` semantics, code-point request limits, generated prompt). Parity: candidates
with exact contexts, marked prompt and assembled results/invalid paths **identical on every case,
including the 116 sample candidates** (89 parity tests; a deliberate WINDOW change makes 4 fail).
Behaviour tests (14): health, CORS reject/preflight/headers, content type, declared and streamed
body bound, 404/405, fail-closed limiters, 429 before parsing, malformed/inconsistent/extra-field/
boolean-as-int/too-long/no-text/insufficient requests without AI, unsupported model or mode,
server-owned metadata, exactly one correction, JSON-mode error correctable, provider errors not
retried with numeric code only, quota, per-call timeout, insufficient content, logs without text.
Known deviations: worker/README.md.

**Performance (local workerd, fake AI with run-J selection, sample request 22 KB):**

| Measurement | Python Worker | TS Worker |
|---|---|---|
| per request, warm (TS: full request path; Python: compact pipeline only) | 23.5 ms | **≈ 4.2 ms** |
| first request after start | 72.6 ms (cold imports) | 42.1 ms first POST (module already initialised by a GET) |
| bundle | 8 985 KiB / 2 234 KiB gzip | 1 077 KiB / 149 KiB gzip |

Local wall time is not Cloudflare CPU. Unmeasured: TS CPU on Cloudflare, module initialisation in
isolation, the AI binding and timeout paths, cross-request isolate reuse. A TS deploy would need
`wrangler tail` CPU checks on health/invalid requests first.

**Model check:** `@cf/meta/llama-3.1-8b-instruct` is **absent** from the account catalogue
(69 models; `wrangler ai models schema` → 6002 "Model schema not found"); only the incompatible
`-fp8` variant exists. Recorded as a blocker; **0 provider calls** in this checkpoint; no other
model tried.

**Proposed next step (for review):** deploy the TS Worker with `cd worker && npx wrangler deploy`
(same name, bindings and model; rollback `cd backend && uv run pywrangler deploy` or
`npx wrangler rollback` to `a4695cc8`), measure CPU without AI, then ONE public sample analysis.
The 70B latency risk (one public timeout at 40 s) is independent of the runtime and remains.

## Stability checkpoint (docs/REVIEW_STABILITY.md) — previous snapshot follows

**History:** with full storage the default browser path made history unavailable; failed
deletions could be shown as done; a save that fit nothing removed the stored list. Fixed in
`127274b` with regressions through browserStorage/useHistory/App (two failed before the fix).

**CPU (no AI calls), sample contract 22 KB / 116 candidates, fake model answer rebuilt from run J:**

| Measurement | Before memo | After memo (`488927e`) |
|---|---|---|
| CPython: extract_candidates (warm) | 19.2 ms | 10.0 ms |
| CPython: full POST through FastAPI/ASGI (warm / first) | 22.4 / 29.1 ms | 13.6 / 19.6 ms |
| local workerd (Pyodide): pipeline per analysis | 41.6 ms | 23.5 ms |
| local workerd: extraction | 38.1 ms | 20.3 ms |
| local workerd: request validation | 0.1 ms | 0.1 ms |
| local workerd: first request after start (cold imports) | 89.7 ms | 72.6 ms |
| Cloudflare (deployed, before memo): GET /api/health | 6–18 ms CPU | — |
| Cloudflare: POST full sample, invalid at validation (no extraction, no AI) | 16 / 29 / 49 ms CPU | — |
| Cloudflare: POST analyze, AI timeout (run L) | 303 ms CPU, 40.0 s wall | — |

Local workerd figures are client wall-time per repeated iteration, not Cloudflare CPU metrics;
the fake answer skips the AI binding, JS↔Python conversion of the AI result and the timeout path.
The hotspot was `_is_table_row` (496 calls for 116 candidates); remaining cost is spread over
number/date parsing and contexts. Conclusion: **even a request that never reaches extraction
costs 16–49 ms CPU on Cloudflare in the Python Worker (Pyodide + FastAPI + Pydantic), above the
10 ms Free limit; extraction adds ~20 ms more.** Python optimisation alone cannot reach 10 ms.

**Model experiment `@cf/meta/llama-3.1-8b-instruct-fp8` (local override, sample only):** two
calls, both rejected before inference — first `provider_unavailable` after 384 ms (code not yet
logged), second code **5025** after 129 ms (`3ff21cf` logs only the numeric code). The model is
not in Cloudflare's JSON Mode list (only `@cf/meta/llama-3.1-8b-instruct` without fp8 is), and
the compact contract requires `response_format: json_schema`. Verdict: **incompatible**; offer
not run; 2 of 4 calls used; no tokens reported; profile removed (`18d9b55`). No other model tried.

## Decision

1. Production stays on the deployed 70B compact Worker until review.
2. Proposed next deployment (behaviour-preserving, for review): backend at `18d9b55` with the same
   config (70B, compact) — includes the CPU memo and numeric error codes; frontend at HEAD with the
   storage-full history fix. It lowers CPU but does **not** make Free CPU compliant and does not
   fix 70B latency (one public timeout).
3. Architectural blocker: Python Workers CPU on Free. Smallest viable free alternative: a thin
   TypeScript Worker with equivalent server-side validation — Zod schemas and limits already exist
   in the frontend; port `numbers.py` (≈160 lines), `candidates.py` (≈330), the compact prompt,
   selection validation and assembly (≈450), CORS/body limit/rate limiting (≈230) and the key
   regression tests (numbers, contexts, names, markers, injection). Estimated 1–2 working days;
   CPU must then be re-measured on Cloudflare. Not started.
4. Model latency: a faster JSON-mode-compatible model must come from the official JSON Mode list
   (e.g. `@cf/meta/llama-3.1-8b-instruct`, availability to be confirmed) — a separate, reviewed
   experiment; not attempted here.
5. F-08 (long documents) and F-10 (OCR) remain queued and incomplete.

# History — dated checkpoints (oldest first)

## Stage 1 status (2026-10-05, historical)

Date: 2026-10-05. Implementer: Claude Code (Opus, subscription). Reviewer: Codex.
Nothing has been deployed or published. "Tested" below means automated tests or local runs
described here; it never means live Workers AI or GitHub Pages verification.

## Runtime assumptions verified against current Cloudflare docs (2026-10-05)

| Assumption | Source / evidence |
|---|---|
| Python Workers use `pywrangler` + `uv`, flag `python_workers`, `uv run pywrangler dev/deploy` | developers.cloudflare.com/workers/languages/python/ |
| FastAPI entrypoint via the SDK `asgi` adapter, env in `request.scope["env"]` | …/python/packages/fastapi/ and `cloudflare/python-workers-examples` (fastapi, workers-ai) |
| Workers SDK wraps `env` so plain dicts can be passed to bindings | `workers-runtime-sdk` 1.9.2 source (`_EnvWrapper`, `python_to_rpc`) |
| ASGI adapter reads the full request body before calling the app | `workers/asgi.py` `process_request` (hence the entrypoint body bound) |
| AI binding `"ai": {"binding": "AI"}` | …/workers-ai/configuration/bindings/ |
| JSON mode: `response_format: {type: "json_schema", json_schema}`; Llama 3.3 70B fp8-fast listed; may fail with "JSON Mode couldn't be met"; no streaming | …/workers-ai/features/json-mode/ |
| Rate Limiting binding: `limit({key})` → `{success}`, period 10 or 60 s, per-location, eventually consistent | …/workers/runtime-apis/bindings/rate-limit/ |
| Workers Free: 10 ms CPU/request, 128 MB, 100k requests/day | …/workers/platform/limits/ |
| Local `pywrangler dev` vendors packages for **Python 3.14** (generated `pylock.toml` requires `>=3.14.2`) | observed locally; CI tests run on CPython 3.13 |
| AI binding in local dev always needs a remote Cloudflare session | observed: `wrangler dev` failed without `CLOUDFLARE_API_TOKEN` (see Failures) |

Free-plan compatibility (CPU per request with FastAPI + Pydantic) is **still a hypothesis**.

## Requirements F-01 … F-10

| ID | Requirement | State | Evidence |
|---|---|---|---|
| F-01 | Drag & drop and chooser, PDF ≤10 MB | Implemented, tested | `FileDropzone`; `checkFile` (type/extension, 10 MiB boundary), `%PDF-` signature; Vitest `files.test.ts`, `useAnalysisFlow.test.tsx`; browser: docx, fake .pdf, >10 MB, corrupt, password-protected all rejected with Polish messages |
| F-02 | Text-layer extraction per page | Implemented, tested locally | pdf.js in browser, `itemsToText` line rebuild + NFC; browser run on the 12-page sample: 12 pages, page 11 detected without text, 20 701 chars, no split Polish diacritics. Multi-column rows interleave (limitation) |
| F-03 | 3–5 sentence summary in document language, no fabrication | Implemented; **quality gate not met; summaries not manually reviewed** | Prompt v2, 70B, evaluator v3: sample 44/65 (twice), synthetic offer 68/72, all failed (latency, missing facts, one wrong date event); summary facts need a human review that has not happened; injection ignored and every amount/date grounded in all runs; long document still misses budget, rejected offer, share capitals, invoice/payment/annex dates and several qualifiers; Polish character corruption seen once (docs/LIVE_AI_RESULTS.md) |
| F-04 | Strict schema, validated before display, one retry within an overall deadline | Implemented, tested (mocks) + one live retry | Pydantic + Zod with shared fixtures; retry only for invalid output and only with ≥ 5 s of the 55 s budget left (controlled-clock tests); live: Gemma's truncated first answer → retry → explicit `AI_TIMEOUT` at 55 s |
| F-05 | Readable result, JSON preview, download | Implemented, tested | `ResultView`; Vitest checks preview string == downloaded string and round-trips through the schema; browser render at 360 px (stub data) |
| F-06 | Empty / loading / error / retry states | Implemented, tested | States in `useAnalysisFlow`; Vitest: stale response ignored after cancel, manual retry only; browser: cancel during analysis returns to ready, error focus |
| F-07 | Public GitHub Pages demo | **Pending** | Workflow builds with `/<repo>/` base and checks the pdf.js worker path; deploy job manual and not run |
| F-08 | Chunking long documents | **Implemented as opt-in experiment, mock-tested only** | `AI_MODE=chunked`: ≤ 8 chunks of ≤ 10 000 chars (up to 64 000 chars, proven + property-tested), overview + chunk calls with ≤ 2 in flight, one deadline, one retry per request, grounded deterministic merge (docs/CHUNKING.md). After review fixes (`63b22b1`, `d284d52`, `0a80133`): merge keeps distinct obligations/events citing one sentence, equal snippets at different offsets and prefix-sharing organisations; currency and qualifiers must be stated at the cited occurrence; unsupported evidence invalidates the chunk within the single retry instead of being dropped. Tests with scripted responses only. **One live trial on the sample (`ed4b255`): AI_TIMEOUT after 40 s — chunk 1 (pages 1–4) hit the 40 s per-call cap; no result. Default remains single-call; chunked mode unaccepted.** |
| F-09 | Local history | **Not implemented** | — |
| F-10 | OCR | **Not implemented** | Partial-analysis warning and fully-scanned error only |

## Security / contract items

| Item | State | Evidence |
|---|---|---|
| No model key; AI via binding only | Done | `wrangler.jsonc` `ai` binding; no key variables exist |
| Bounded body before parse | Done, tested (fixed after review, `ccc0fa5`) | Every request is rebuilt in the entrypoint before the ASGI adapter: only `POST /api/analyze` (path decoded like the adapter) streams ≤ `MAX_BODY_BYTES + 1` bytes; other paths, `/api/analyze/`, other methods and preflight are forwarded without a body. pytest drives `src/worker.py` with fake js/workers modules (body stream never read for 9 route/method cases; 65 MB chunked and 8 MB single-chunk analyze bodies cut at limit+1); ASGI-level no-read test; workerd checks below |
| Origin allowlist from config | Done, tested | pytest + workerd smoke (403 foreign, 204 preflight, ACAO on allowed) |
| Shared rate limiting | Done, locally tested | Rate Limiting bindings; workerd smoke: 5×503 then 429 for one IP (local simulation). **Not verified on Cloudflare.** Production fails closed without bindings (pytest) |
| No document text in logs | Done, tested | whitelist logger; pytest asserts marker text absent |
| Prompt injection | Mitigated, tested structurally | pytest: injected text stays inside the single data block, fake tags neutralised, system prompt unchanged. **Whether Llama obeys is unverified** |
| Metadata ownership | Done, tested | pytest: model-supplied fileName/pages ignored |
| Malformed / incomplete model response | Done, tested (fixed after review, `bd991ae`) | Raw `ModelOutput` validated strictly before normalisation: all 12 keys required, only title/date nullable. pytest: reviewer reproduction → 502 after exactly 2 calls; each missing key → retry → 200 (2 calls) and twice → `AI_INVALID_OUTPUT` (2 calls); 16 wrong-shape cases retried; explicit null/[] valid on first call. Vitest: 200 with invalid body → error, not displayed |
| Provider failure / timeout / quota | Done, tested (mocks) | pytest 502/503/504 mapping, error text classification |
| No `any`, `console.log`, `dangerouslySetInnerHTML` | Enforced | ESLint rules (`no-explicit-any`, `no-console`, restricted JSX attribute); Vitest renders hostile markup as text |

## Commands executed (all passed at the name-fidelity checkpoint)

```
backend$  uv run ruff check .            # All checks passed
backend$  uv run ruff format --check .   # all files formatted
backend$  uv run pytest -q               # 439 passed (422 before name fidelity, 96 in Stage 1)
backend$  uv run python -m evaluation.oracle --case sample_contract --case synthetic_offer_pl   # PASS 70/70, 73/73
backend$  uv lock --check                # lock up to date
frontend$ npm run lint                   # 0 problems (--max-warnings=0)
frontend$ npm run format:check           # all files formatted
frontend$ npm run typecheck              # 0 errors
frontend$ npm test                       # 90 passed (10 files)
frontend$ VITE_BASE_PATH=/pdf-insight/ npm run build   # ok; worker at /pdf-insight/assets/pdf.worker.min-*.mjs
backend$  uv run pywrangler dev --config wrangler.smoke.jsonc   # workerd/Pyodide smoke, see below
```

Local workerd smoke (no AI binding, `ENVIRONMENT=production`): `/api/health` 200 in ~4 ms;
valid request → 503 `SERVICE_MISCONFIGURED` (after rate limit + Pydantic validation ran in
Pyodide); inconsistent pages → 400; scanned → 422; foreign origin → 403; preflight → 204;
wrong content type → 415; chunked oversize → 413; 7 rapid requests → `503×5, 429×2`.

Review-fix workerd checks (20 MB chunked uploads with curl, after `ccc0fa5`):

| Request | Result |
|---|---|
| `POST /api/analyze/` (trailing slash) | 404 in ~5 ms, 0 bytes uploaded |
| `POST /unknown` | 404 in ~4 ms, 0 bytes uploaded |
| `PUT /api/analyze`, `PATCH /api/health` | 405 in ~4 ms, 0 bytes uploaded |
| `DELETE /api/analyze`, `GET /api/analyze` | 405 |
| `OPTIONS /api/analyze` (preflight) | 204 |
| `POST /api/analyze`, `POST /api/%61nalyze` | 413 after ~1 s (body read stops at the limit; curl had pushed ~2 MB into socket buffers) |
| previous smoke script | unchanged results; no Python traceback in the workerd log |

404/405 responses use FastAPI's default `{"detail": ...}` body, not the API error envelope.

Browser checks (in-app Chromium, 360×780): real pdf.js extraction of the sample contract; error
paths against the local Worker; success rendering and cancel against a local stub that returned a
contract fixture (**stub = mock, not AI output**). No horizontal overflow at 360 px.

## Failures and fixes during Stage 1

1. `pywrangler dev` with the AI binding failed: *"In a non-interactive environment, it's necessary to
   set a CLOUDFLARE_API_TOKEN"*. Not worked around (no credentials handled); added
   `wrangler.smoke.jsonc` for credential-free runtime checks.
2. First body precheck required `Content-Length`; in workerd a missing header is `JsNull` (crash →
   500) and the wrangler proxy forwards large bodies chunked. Fixed: length optional, entrypoint
   reads the stream with a `limit + 1` cap.
3. Declared oversize body without `Expect: 100-continue`: Worker logs `413`, but the local
   miniflare proxy reports *"Network connection lost"* (500) because the unread upload is dropped.
   With `Expect: 100-continue` the client gets a clean 413. Production behaviour unverified; the
   frontend never sends over-limit bodies.
4. A shared sentence fixture had a wrong expected max (4 instead of 5); fixed the fixture after
   checking the rule by hand.
5. Ruff reformatted pywrangler's generated `python_modules/`; deleted it, excluded it from ruff and
   git (`python_modules/`, `pylock.toml`).
6. pdf.js 6 removed `isEvalSupported`; option dropped.
7. Fixture loader broke under jsdom (`import.meta.url` not `file:`); switched to `process.cwd()`.
8. Render test exposed tables without accessible names; added captions.
9. In-app preview server runner could not access `~/Documents` (macOS "Operation not permitted");
   servers were started from the shell instead.

### Fixed after Codex review (docs/REVIEW_STAGE1.md)

10. **P1 unbounded bodies** (`ccc0fa5`): only `POST /api/analyze` was bounded; trailing slash,
    unknown paths and other methods reached the adapter, which queues the whole body. Also
    `read_limited` retained a whole chunk before truncating. Fixed as described above; the new
    entrypoint tests fail on the previous `worker.py` (10 of 16 failed when checked).
11. **P1 incomplete model output accepted** (`bd991ae`): `build_result` used `get(..., [])`
    defaults, so missing keys looked like empty results and no retry happened. Reproduced with the
    reviewer's case (HTTP 200, 1 call) before fixing; 20 of the 45 new tests failed on the old
    code (one of them only because `ModelOutput` did not exist yet).
12. While writing the fix-1 tests, one test passed `str` header keys to a callback that receives
    `bytes`; corrected the test. A local curl run first failed because zsh does not word-split
    `$O`; rerun with explicit arguments.

## Live AI checkpoint (local pywrangler, real binding) — see docs/LIVE_AI_RESULTS.md

Three analyses of the sample contract on a Workers Free account without a payment method:
run 1 → 504 `AI_TIMEOUT` with the committed 25 s per-attempt timeout; runs 2–3 (local 60 s
override) → 200, identical valid results, 1 model call each, 9 119 / 622 tokens (≈ 371 neurons),
server 30.1–30.5 s, upload-to-render 30.4–30.8 s. Evaluation 20/24: type, language, date, parties,
page-11 warning, injection resistance and grounding pass; gross amount, signing/invoice/payment
dates missing. The live retry path was not exercised. (The 20/24 rubric is retired; re-scored with
the atomic rubric this result is 22/45.)

## AI tuning checkpoint — see docs/LIVE_AI_RESULTS.md

Five model calls (limit six): prompt v2 on Llama 3.3 70B → sample 30/45 in 35.4 s and 30.7 s,
synthetic offer 51/53 in 31.3 s; Gemma 4 26B-A4B (the requested Llama 3.1 8B is not in the catalog)
→ first answer cut at 2 048 tokens, retry stopped by the 55 s deadline (`AI_TIMEOUT`). No candidate
meets quality and latency; the 70B stays the default. Recommended next option for review:
page-based chunk extraction + deterministic merge (F-08).

## Evaluator v3 and offline re-evaluation — see docs/LIVE_AI_RESULTS.md

The audit (docs/REVIEW_EVALUATION.md) showed the evaluator accepted wrong date events, keyword-soup
contexts, a wrong file name and nonsense summaries, and mis-parsed numbers. Reproduced with six
failing tests, then fixed (`6ccc699`, `aaadd61`, `dc495b7`): bounded currency-aware number
parsing, page+snippet evidence for every expected fact, qualifiers and events judged on the same
entry, schema/metadata/coverage checks, and explicit `needs_manual_review` for summary, key points,
context meaning and language fidelity (never counted as passed). `run_live --check` exits 0/1/2.
All saved responses re-scored offline: every run is **failed** (baseline 33/63, prompt-v2 70B
44/65 on the sample, 68/72 on the synthetic offer; Gemma and baseline 1 failed by HTTP 504).
Scores are per-document check counts, not accuracy; no result is accepted.

## Chunked extraction checkpoint — see docs/CHUNKING.md

Implemented without live AI calls; default unchanged (`AI_MODE=single`). Offline plan for the
sample contract: 3 chunks (pages 1–4, 5–9, 10 and 12) + overview = 4 calls, estimated ≈ 930–1 110
neurons (single mode measured ≈ 406). Main risk: two call rounds at concurrency 2 with ~30 s per
70B call exceed the 55 s budget, so the sample would likely time out unless chunk calls are
faster — to be measured in the bounded live comparison.

## Chunking review fixes — docs/REVIEW_CHUNKING.md

Three defects reproduced first with 20 regression tests (16 failed on the reviewed code; output in
`.local/live/chunk-review-regressions-before-fix.txt`), then fixed in separate commits:
`63b22b1` merge identity (same occurrence + identical meaning only; exact offsets; legal-form-only
organisation alias), `d284d52` unsupported evidence invalidates the chunk inside the single
correction retry, `0a80133` currency/qualifiers resolved from the cited source occurrence. Retry
budget (1 per request), deadline, cancellation and the single-call default are unchanged.

## Chunked live trial — see docs/LIVE_AI_RESULTS.md

One analysis of the sample with a local `AI_MODE=chunked` override (limits unchanged): 4 calls
started (≤ 5 allowed), overview ok in 20.3 s (8 934 / 437 tokens), chunk 1 timed out at the 40 s
per-call cap, chunk 2 and chunk 3 cancelled → `AI_TIMEOUT` (504) after 40.0 s, no result, no
retry used. Throughput ≈ 20–29 output tokens/s, so per-call time follows output length and the
evidence-rich chunk schema makes the densest chunk slower than the whole single call. New defect
recorded: a queued call (chunk 3) was dispatched for 3 ms after the failure before cancellation.

## Compact candidate-selection trial — see docs/LIVE_AI_RESULTS.md

`1b929d6` fixed the cancellation race (terminal-failure latch; 3 of 5 new tests failed on the old
code). `82bb960` added the opt-in `AI_MODE=compact`: code extracts candidate amounts/dates with
exact offsets and source contexts, one model call selects IDs, values/contexts are copied from the
source. One live sample run: 200 in 22.6 s, 1 call, 9 727 / 740 tokens (≈ 411 neurons); evaluator
v3 failed 61/69 (legal forms dropped; 5 "contradicting qualifier" checks that also fail with a
perfect selection because source sentences state net/VAT/gross together); manual review failed on
contexts (wrong "200 PLN" from "295\n200,00" split across lines, 9 footer dates selected). Gate
not met, so the synthetic offer was not run (1 of 4 calls used). Default remains single-call.

## Compact correction (docs/REVIEW_COMPACT.md) — see docs/LIVE_AI_RESULTS.md

`fdf6e47`: line-wrapped numbers reconstructed or rejected (never the suffix), currency after a
line break, contexts that mark the selected »occurrence« and are cut around it, flattened-table
rows with headers, repeated page/version footers excluded, dedup of identical facts, legal-form
resolution to a unique full name, prompt `compact-v2`. `028c53a`: evaluator v4 (qualifiers of the
marked occurrence only; negative regressions kept; manual subcheck for an unnamed issue-date
header) and `evaluation/oracle.py`. `cc070c1`: live report named after the evaluator version.
Offline oracle passed on both cases (68/68, 71/71 + 1 manual subcheck). One live sample call:
200 in 23.8 s, 9 822 / 716 tokens, evaluator v4 69/69 automatic; manual review (Claude, AI)
failed key points (verbatim copies of the summary). Gate not met, synthetic offer not run
(1 of 4 calls used). The model selects nearly every candidate (76/77 amounts, all dates).
F-08 compact remains experimental; default `single`.

## Compact name fidelity and offer trial — see docs/LIVE_AI_RESULTS.md

`3fb0659`: person names must be written in the source (any attested inflection; mixed/unknown
names use the single correction; logs carry positions only). `6737f8e`: eval-v5 grounds names
(saved run G re-scored: "Marek Zielińskiego" flagged). Run G's key points: overlap with the
summary is now an editorial, nonblocking issue (review reinterpretation; the historical verdict
stays recorded). Live synthetic offer (run H, 1 call): 200 in 14.0 s, all 73 automatic checks,
exact selection, injection excluded — but internal markers ("⟦A5⟧96 000,00 zł") leaked into the
summary and key points: language fidelity failed, so the sample was not repeated (1 of 4 calls).
`e2c20c4` removes markers copied before their value and treats any other marker as invalid
output; `093f856` (eval-v6) fails leaked markers. Not re-measured live yet.

## Release checkpoint (docs/REVIEW_RELEASE_CHECKPOINT.md) — see docs/DEPLOYMENT.md

Live on current compact (`compact-v4`): offer run I 11.5 s, 74/74; sample run J 26.2 s, 71/71;
both accepted with AI-assisted source review (Claude). `c775866`: compact is the release mode in
`wrangler.jsonc` / `.dev.vars.example`; `single` remains the code fallback, `chunked` an
unvalidated experiment. Backend deployed to the Free account:
https://pdf-insight-api.pdf-insight-api.workers.dev (version `a4695cc8`). Health, CORS allow /
reject verified without model calls. One deployed sample analysis through the real frontend:
upload-to-render 25.3 s, 71/71, page-11 warning and JSON export verified. Calls this checkpoint:
3 of 6 (2 local + 1 deployed, the last inferred from timing).

## Release gates as of the backend deployment (2026-10-06, superseded by the snapshot)

| Gate | State |
|---|---|
| Latency < 30 s | compact: 11.5–26.2 s locally, 25.3 s deployed backend with local frontend — not yet on the public Pages URL; the sample has only ~5 s margin |
| Free CPU per request | **not observed** (dashboard Metrics needed); no resource-limit error seen |
| AI quota | ≈ 410 neurons per sample analysis (own estimate); actual usage unknown |
| CORS | verified on the Worker (Pages origin allowed, others 403); requests without Origin are only rate limited |
| Rate limiting | Codex independently observed production 429 on invalid-body requests, no AI calls (2026-10-06); eventually consistent, per location |
| Frontend | GitHub Pages not published; live URL, pdf.js worker, screenshot, 14-day availability open |
| Quality | long sample: model selects nearly every candidate (verbose); two-column/whitespace-table mapping left to the reader; people list completeness varies |
| Old single mode | baseline only: 30.1–35.4 s locally, sample 44/65 (eval-v3) |
| F-08 long documents | **open** — compact rejects > 30 000 characters (explicit 413); chunked unvalidated |
| F-09 local history | **not implemented** |
| F-10 OCR | **not implemented** (partial-analysis warning only) |

## Next steps proposed at that checkpoint (superseded)

1. User reads Worker CPU time/logs in the Cloudflare dashboard; then the separately authorised
   publication step: public repository, `VITE_API_URL`, GitHub Pages deploy, live checks.
2. Tune prompt/model only from measured failures; record in AI_LOG.md.
3. GitHub repo + Pages deploy via manual workflow; README demo link and screenshot.
4. SHOULD: F-08 chunking (page-based, merge + dedupe), F-09 local history. COULD: F-10 OCR for
   image-only pages (decide provider/privacy first).
