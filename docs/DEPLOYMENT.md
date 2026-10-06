# Backend deployment — 2026-10-06

Backend Worker only. The frontend (GitHub Pages) and the public repository are **not** published
yet; that is the next, separately authorised step.

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
| Production 429 | **not verified** on Cloudflare (would spend analysis calls); 429 seen only in local workerd simulation and tests |

## Deployed analysis through the real frontend (one request)

Local frontend (`vite`, `VITE_API_URL` = the Worker URL, origin `http://localhost:5173` allowed
temporarily), sample contract dropped as a file:

| Measurement | Value |
|---|---|
| Upload-to-render (drop → result rendered) | **25.3 s** (PDF.js text extraction 0.26 s, request → render 25.1 s) |
| Result | validated by Zod and rendered; evaluator v6 **71/71** automatic checks; AI-assisted source review (Claude): pass |
| Page 11 warning | shown ("Analiza częściowa. Strona 11 (z 12) nie zawiera tekstu…") |
| JSON export | `Test_PDF_Insight_umowa_14-2026-analiza.json`, `application/json`, identical to the preview (captured without saving a file) |
| Model calls | not read from Worker logs; a corrective second call would not fit the 25 s duration, so 1 call is inferred, not observed |
| Worker CPU time | **not observed.** The request finished without a resource-limit error, which does not prove compliance with the Free 10 ms CPU limit. Check: Cloudflare dashboard → Workers & Pages → `pdf-insight-api` → Metrics → CPU time (and Logs, observability enabled) |
| AI usage | ≈ 410 neurons per sample analysis by own estimate; dashboard usage **unknown** |

Evidence (git-ignored): `.local/live/deployed/K-deployed-sample/` (exported result, metadata,
evaluator report, AI review).

## Remaining before release

1. Read CPU time and errors for the deployed requests in the dashboard (user, logged in).
2. Create the public repository, set repository variable
   `VITE_API_URL=https://pdf-insight-api.pdf-insight-api.workers.dev`, enable Pages ("GitHub
   Actions"), run the CI workflow with `deploy`; the Pages origin `https://iamkiryl.github.io` is
   already allowed. Then measure upload-to-render on the public URL, check pdf.js worker loading,
   take a screenshot, watch 14-day availability.
3. Production 429 and cross-location rate limits remain unverified.
4. Open delivery decisions: F-08 long documents (compact rejects text above 30 000 characters with
   an explicit 413; chunked is unvalidated), F-09 local history, F-10 OCR.
