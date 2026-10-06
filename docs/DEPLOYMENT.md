# Deployment

## Current state (2026-10-06, 12:20 Warsaw)

| Item | State |
|---|---|
| Frontend | https://iamkiryl.github.io/pdf-insight/ (GitHub Pages, CI run 37445769851, commit `54515a5`; F-09 history incl. the storage-full fix) |
| Backend | https://pdf-insight-api.pdf-insight-api.workers.dev — **TypeScript Worker** version `d7e5ae75-a043-45c7-8f7f-2ecac09e9d74` (app code `17593aa`), 70B, compact; rollback: TS `dd6a5db2-5c7d-4b1f-b037-b8608459087e`, Python `a4695cc8-ac6c-47a9-9253-6facf931c2b9` (docs/RUNTIME.md) |
| Not deployed | Python `488927e`/`3ff21cf` (superseded by the TS runtime; kept as reference) |
| Production 429 | **observed** by Codex on 2026-10-06 ~06:59 UTC with invalid-body POSTs (no model calls); per-location and eventually consistent, not an exact cap |
| CPU | TS: health 0–1 ms, invalid full-size 5 ms, analysis 37 ms (P) / 39 ms (Q); earlier Python: 6–18 / 16–49 / 303 ms — above the documented 10 ms Free limit |
| Public analysis | TS P: 26.5 s, 71/71, accepted; TS Q: 30.7 s (over target), 70/71; earlier Python L: timeout (40 s) |

The sections below are dated records of each deployment step.

# Backend deployment — 2026-10-06 (historical record)

At the time of this section the frontend (GitHub Pages) and the public repository were not yet
published (they were published later the same morning, see below).

## What is deployed

| Item | Value |
|---|---|
| URL | https://pdf-insight-api.pdf-insight-api.workers.dev |
| Worker | `pdf-insight-api` (did not exist on the account before; nothing was overwritten) |
| Account | the user's personal Cloudflare account, Workers Free without payment method (confirmed by the user on 2026-10-05; not re-checkable from the CLI without reading the token; no billing setting was touched) |
| Current version | `a4695cc8-ac6c-47a9-9253-6facf931c2b9` (2026-10-06 06:45 UTC), built from commit `c775866` |
| Earlier versions | `fb88ede1…` (first deploy, same config), `81b7d789…` (temporary: + `http://localhost:5173` origin for the frontend test, replaced 2 minutes later) |
| Upload | 8 985 KiB / gzip 2 234 KiB (Free limit 3 MB compressed); reported startup 2 325 ms |
| Config (`backend/wrangler.jsonc`) | `ENVIRONMENT=production` (fail closed), `ALLOWED_ORIGINS=https://iamkiryl.github.io`, `AI_MODE=compact`, model `@cf/meta/llama-3.3-70b-instruct-fp8-fast`, 40 s per call / 55 s per request, `MAX_BODY_BYTES=262144`, observability on |
| Bindings | `AI` (Workers AI), `ANALYZE_IP_LIMITER` 5/60 s, `ANALYZE_GLOBAL_LIMITER` 30/60 s (Rate Limiting) |
| Secrets | none exist or are needed (AI via binding) |

## Commands used

```bash
cd backend
uv run pywrangler deploy --dry-run   # bundle and bindings check, nothing uploaded
uv run pywrangler deploy             # production config from wrangler.jsonc
# temporary, for the local real-frontend test only (removed by the next plain deploy):
uv run pywrangler deploy --var "ALLOWED_ORIGINS:https://iamkiryl.github.io,http://localhost:5173"
uv run pywrangler deploy             # back to the committed config
npx wrangler deployments list        # versions
npx wrangler rollback                # if a release must be reverted
```

## Verification without model calls

| Check | Result |
|---|---|
| `GET /api/health` | 200 in ~1 s: `environment: production`, `aiBinding: true`, `rateLimiter: true`, `mode: compact` |
| Preflight from `https://iamkiryl.github.io` | 204 with `Access-Control-Allow-Origin` for that origin |
| Preflight / POST from `https://evil.example` | 403 / 403 `ORIGIN_NOT_ALLOWED` |
| POST from `http://localhost:5173` (current version) | 403 (temporary origin removed) |
| POST without `Origin` | reaches validation (400 for an invalid body): by design CORS only restricts browsers; direct clients are limited by the rate limiters only |
| Production 429 | not verified at this step (later observed by Codex without model calls, see Current state) |

## Deployed analysis through the real frontend (one request)

Local frontend (`vite`, `VITE_API_URL` = the Worker URL, origin `http://localhost:5173` allowed
temporarily), sample contract dropped as a file:

| Measurement | Value |
|---|---|
| Upload-to-render (drop → result rendered) | **25.3 s** (PDF.js text extraction 0.26 s, request → render 25.1 s) |
| Result | validated by Zod and rendered; evaluator v6 **71/71** automatic checks; AI-assisted source review (Claude): pass |
| Page 11 warning | shown ("Analiza częściowa. Strona 11 (z 12) nie zawiera tekstu…") |
| JSON export | `Test_PDF_Insight_umowa_14-2026-analiza.json`, `application/json`, identical to the preview (captured without saving a file) |
| Model calls | **not observed** (Worker logs were not read for this request; elapsed time does not establish the count) |
| Worker CPU time | **not observed.** The request finished without a resource-limit error, which does not prove compliance with the Free 10 ms CPU limit. Check: Cloudflare dashboard → Workers & Pages → `pdf-insight-api` → Metrics → CPU time (and Logs, observability enabled) |
| AI usage | ≈ 410 neurons per sample analysis by own estimate; dashboard usage **unknown** |

Evidence (git-ignored): `.local/live/deployed/K-deployed-sample/` (exported result, metadata,
evaluator report, AI review).

## Remaining before release (as of the backend deployment — items 2 and 3 since done)

1. Read CPU time and errors for the deployed requests in the dashboard (user, logged in).
2. Create the public repository, set repository variable
   `VITE_API_URL=https://pdf-insight-api.pdf-insight-api.workers.dev`, enable Pages ("GitHub
   Actions"), run the CI workflow with `deploy`; the Pages origin `https://iamkiryl.github.io` is
   already allowed. Then measure upload-to-render on the public URL, check pdf.js worker loading,
   take a screenshot, watch 14-day availability.
3. Production 429 and cross-location rate limits remain unverified.
4. Open delivery decisions: F-08 long documents (compact rejects text above 30 000 characters with
   an explicit 413; chunked is unvalidated), F-09 local history, F-10 OCR.

# Public repository and GitHub Pages — 2026-10-06

| Item | Value |
|---|---|
| Repository | https://github.com/iamKiryl/pdf-insight — created public by `gh repo create` (did not exist before), full history pushed (no squash) |
| Pre-publication audit | all 62 commits: one author/committer identity (the user's personal address), no removed files, no secrets/tokens/keys, no work e-mail, no absolute local paths, no PDFs; `.local/`, `.dev.vars`, `.claude/` ignored; brief and test PDF not in the repository (the sample case keeps short evidence snippets only) |
| CI fix | `astral-sh/setup-uv@v10` tag does not exist (only release tags such as `v10.2.0`) → pinned (`85112f8`); other action tags verified to exist |
| Repository variable | `VITE_API_URL=https://pdf-insight-api.pdf-insight-api.workers.dev` |
| Pages | enabled with `build_type=workflow`: https://iamkiryl.github.io/pdf-insight/ |
| CI runs | push run https://github.com/iamKiryl/pdf-insight/actions/runs/37427902569 (4 jobs passed, deploy skipped); dispatch `deploy=true` run https://github.com/iamKiryl/pdf-insight/actions/runs/37428051869 — frontend lint, frontend typecheck/tests, backend lint/tests, build, deploy: all success, commit `85112f8` |
| CORS | account `iamKiryl` → origin `https://iamkiryl.github.io` already in the Worker; no temporary origin left |

## Public demo verification (anonymous visitor)

Headless Chrome with a fresh profile (and the in-app browser for the initial state); the file was
set on the real `<input type=file>` (CDP `DOM.setFileInputFiles`).

| Check | Result |
|---|---|
| Initial state | title, steps, data notice, upload area, empty history; assets under `/pdf-insight/` |
| pdf.js worker | `/pdf-insight/assets/pdf.worker.min-*.js` 200 `application/javascript`; sample read in 0.49 s (12 pages, 20 701 chars) |
| Page-11 warning | shown before analysis and on the result |
| Error handling | non-PDF file → "To nie jest plik PDF", no network request; AI timeout → "Analiza trwała zbyt długo…" with retry |
| Mobile 360 px | no horizontal page scroll (steps 2×2, stacked tables) |
| **Real sample analysis (one allowed)** | **failed: AI_TIMEOUT.** `wrangler tail`: POST `/api/analyze` from the Pages origin, model call `compact` attempt 1 `timeout` after 40 000 ms, `modelCallsStarted 1, completed 0`, response 504, Worker wall 40 005 ms, **CPU 303 ms**. Not retried (rule: no retry loop) |
| History with existing local data | the saved deployed result K written to the visitor's localStorage, page reloaded: entry listed, reopened in the result view, page-11 warning, 76 amounts, JSON export identical to the stored result, **0 requests** to the Worker during history use |

## Worker CPU and logs

Only `wrangler tail` (live) is accessible without reading credentials; dashboard metrics and past
logs need the user's dashboard session. Observed: analyze (timeout) 303 ms CPU, OPTIONS 21 ms,
health 6 ms; no resource-limit exception. CPU for a *successful* analysis and aggregates are not
observed. The Free plan documents 10 ms CPU per request: compatibility is **unverified** and the
observed value is a risk to resolve (e.g. check the dashboard; consider the Python cold-start cost).

Evidence (git-ignored): `.local/live/deployed/L-public-sample/` (numeric tail summary, run JSON,
screenshots).
