# PDF Insight

Upload a PDF, get a factual summary and structured data (document type, title, date, key points,
organizations, people, amounts, dates, keywords) as validated JSON you can download.

> **Status: Stage 1 MVP, not deployed.** No public demo URL exists yet, the AI path has not been
> run against live Workers AI, and the <30 s target is unmeasured. See
> [docs/STATUS.md](docs/STATUS.md) for what is implemented, tested and pending.

## Architecture

```
Browser (GitHub Pages, React SPA)                Cloudflare Python Worker (FastAPI)
┌──────────────────────────────────┐   HTTPS    ┌─────────────────────────────────────────┐
│ PDF ≤10 MB stays in the browser  │  JSON:     │ entrypoint: bound body (≤256 KiB)       │
│ pdf.js → text per page           │  pages +   │ CORS allowlist → Rate Limiting bindings │
│ pages without text detected      │  metadata  │ Pydantic request validation             │
│ limits checked, nothing truncated│ ─────────► │ prompt (document = untrusted data)      │
│ Zod validates every response     │ ◄───────── │ env.AI.run(Llama 3.3 70B, JSON mode)    │
│ result view + JSON download      │  result    │ Pydantic output validation, 1 retry     │
└──────────────────────────────────┘            └─────────────────────────────────────────┘
```

- **frontend/** — React 19, Vite, TypeScript strict. `src/components` (UI), `src/lib` (contract,
  extraction, validation, flow state), `src/api` (HTTP client).
- **backend/** — FastAPI on Cloudflare Python Workers (Pyodide). `src/worker.py` is the Workers
  entrypoint; `src/pdf_insight/` is plain FastAPI/Pydantic code that runs and is tested on CPython.
- **contracts/** — the API contract, ISO code lists, numeric limits and accepted/rejected fixtures
  shared by pytest and Vitest. Details: [contracts/README.md](contracts/README.md).

### Key decisions

| Topic | Decision |
|---|---|
| AI access | Workers AI **binding** (`env.AI`). There is no model API key anywhere — not in code, config, the browser or CI. |
| Model | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` with `response_format: json_schema` (listed as supported in Cloudflare's JSON mode docs, 2026-10-05). Configurable via `AI_MODEL`. |
| Data flow | Only extracted text leaves the browser; the PDF itself does not. Nothing is stored server-side. The UI shows a Polish notice before the user starts the analysis. |
| Untrusted input | Page text is wrapped in `<document>/<page>` tags, tag names inside the text are neutralised, and the system prompt treats instructions inside the document as content. Results are rendered as text only (no `dangerouslySetInnerHTML`). |
| Ownership | `document.fileName` and `document.pages` come from the validated request, never from the model. |
| Validation | The raw model JSON is validated first (all requested keys present, strict types), then normalised and validated against the public contract: strict Pydantic (backend) and Zod (frontend) with unknown keys rejected; both run the same fixture files. Exactly one backend retry on invalid model output; the browser never retries on its own. |
| Summary length | 3–5 sentences checked with a conservative sentence-count interval that handles `sp. z o.o.`, `S.A.`, decimals and initials (see contracts/README.md). |
| Missing title | Deterministic neutral label in the document language (`Dokument bez tytułu`, `Untitled document`, …) with `analysis.titleFallback = true`. |
| Scans | Pages without a text layer are listed in `analysis.pagesWithoutText` and shown as a partial-analysis warning; a fully scanned PDF gets an actionable error. No OCR yet. |
| Body limit | The Workers ASGI adapter buffers the body before FastAPI runs, so the entrypoint rebuilds **every** request first: only `POST /api/analyze` reads its body (rejected from an oversized declared `Content-Length` without reading, otherwise streamed and abandoned after `MAX_BODY_BYTES + 1` bytes); all other paths and methods are forwarded without a body. Middleware enforces the same policy again. |
| Rate limiting | Cloudflare Rate Limiting bindings: 5 req/60 s per client IP and 30 req/60 s global. Counters are per Cloudflare location and eventually consistent (documented by Cloudflare). In production the API fails closed (503) if a binding is missing or errors. |
| CORS | Origin allowlist from `ALLOWED_ORIGINS`, read per request. CORS is not treated as protection against direct requests; rate limits are. |

## Local development

Prerequisites: Node 22+, [uv](https://docs.astral.sh/uv/) (Python 3.13+).

```bash
# frontend
cd frontend
npm ci
cp .env.example .env.local   # optional; dev defaults to http://localhost:8787
npm run dev                  # http://localhost:5173
npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
```

```bash
# backend unit tests and lint (no Cloudflare account needed)
cd backend
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

```bash
# run the real Worker locally in workerd/Pyodide WITHOUT credentials (no AI binding):
cd backend
npm ci
uv run pywrangler dev --config wrangler.smoke.jsonc
# /api/health, validation, CORS, body limit and the local rate limiter work;
# /api/analyze returns 503 SERVICE_MISCONFIGURED because there is no AI binding.
```

```bash
# full local Worker with Workers AI (requires a human to run `npx wrangler login` first;
# Workers AI calls always go to Cloudflare and use the account's quota)
cd backend
cp .dev.vars.example .dev.vars
uv run pywrangler dev
```

### Configuration

| Where | Name | Purpose |
|---|---|---|
| `backend/wrangler.jsonc` vars | `ENVIRONMENT` | `production` (default, fail closed) or `development` (adds localhost origins, allows running without rate-limit bindings) |
| | `ALLOWED_ORIGINS` | comma-separated origins, e.g. `https://<user>.github.io` (no path) |
| | `MAX_BODY_BYTES`, `AI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_MAX_TOKENS` | limits and model settings |
| `backend/.dev.vars` (git-ignored) | same names | local overrides; see `.dev.vars.example` |
| `frontend/.env.local` (git-ignored) | `VITE_API_URL` | public backend URL (not a secret) |
| GitHub repository variable | `VITE_API_URL` | backend URL baked into the Pages build |

No secrets are required by the application. Deploying the Worker needs a Cloudflare login on a
developer machine (or a scoped `CLOUDFLARE_API_TOKEN` stored as a CI secret if backend deployment
is automated later).

## Deployment prerequisites (not done yet)

1. A human logs in to Cloudflare (`npx wrangler login`) and confirms the account is on the Free
   plan with Workers AI available.
2. Set `ALLOWED_ORIGINS` in `backend/wrangler.jsonc` to the GitHub Pages origin, then
   `cd backend && uv run pywrangler deploy`. Check `GET /api/health` shows `aiBinding: true` and
   `rateLimiter: true`.
3. Measure CPU time per request (Workers Free allows 10 ms CPU per request; network wait for the AI
   call does not count) and the end-to-end time on the sample contract and other PDFs.
4. In GitHub: create the public repository, set repository variable `VITE_API_URL`, enable Pages
   with source "GitHub Actions", then run **Actions → CI → Run workflow** with `deploy` checked.
5. Verify the live URL `https://<user>.github.io/<repo>/` loads the pdf.js worker, analyses a PDF,
   and record a screenshot.

## Current limitations

- Not deployed; no live AI verification, CPU/latency/quota measurements or public URL yet.
- No OCR (F-10): image-only pages are reported, not read.
- No chunking (F-08): text over 48 000 characters is rejected with a clear message, never truncated.
- No local history (F-09).
- Text extraction reads multi-column layouts row by row (good for tables, can interleave true
  columns such as side-by-side party details).
- Rate limits are per Cloudflare location and approximate; the daily Workers AI allocation is not
  tracked by the app (exhaustion is reported as `AI_QUOTA_EXCEEDED`).
- Schema validation proves structure, not truth; output quality must be checked on real documents.

## Repository guide

- [docs/PLAN.md](docs/PLAN.md) — requirements analysis and plan (Russian).
- [docs/STATUS.md](docs/STATUS.md) — requirement-by-requirement status, executed checks, gaps.
- [AI_LOG.md](AI_LOG.md) — how AI tools were used, prompts, mistakes and fixes.
