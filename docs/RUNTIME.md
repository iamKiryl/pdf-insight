# Backend runtime: Python Worker (deployed) and TypeScript Worker (candidate)

2026-10-06. Decision source: docs/NEXT_FREE_RUNTIME.md.

| | Python Worker `backend/` | TypeScript Worker `worker/` |
|---|---|---|
| Status | **deployed** (`pdf-insight-api`, version `a4695cc8`, from `c775866`) | candidate, **not deployed** |
| Modes | compact (deployed), single, chunked (experiments) | compact only |
| API, errors, bindings, model | reference | identical (parity tests against Python golden files) |
| CPU evidence | Cloudflare: health 6–18 ms, invalid full-size request 16–49 ms, analyze 303 ms (timeout run); local workerd pipeline 23.5 ms after memo | local workerd: full request ≈ 4.2 ms warm, 42 ms first POST; **Cloudflare CPU not measured** |
| Bundle | 8 985 KiB / 2 234 KiB gzip | 1 077 KiB / 149 KiB gzip |

## Intended replacement (only after review)

The TS config (`worker/wrangler.jsonc`) uses the same Worker name `pdf-insight-api`, the same
`AI` binding, the same rate-limit namespaces (41001, 41002), production fail-closed vars, the
Pages-only origin and the 70B model. Deploying it REPLACES the Python runtime at the same URL:

```bash
cd worker
npm ci && npm run typecheck && npm test
npx wrangler deploy            # replaces pdf-insight-api with the TS runtime
```

Verify afterwards without model calls: `GET /api/health` (expects `"mode":"compact"`), foreign
origin 403, Pages preflight 204; then measure CPU with `npx wrangler tail pdf-insight-api --format json`
on health and an invalid full-size request before any analysis.

## Rollback / Python fallback (explicit, separate)

```bash
cd backend
uv run pywrangler deploy       # redeploys the Python runtime to the same Worker name
# or, for an exact previous version:
npx wrangler rollback          # choose the Python version, e.g. a4695cc8-ac6c-47a9-9253-6facf931c2b9
```

Never run a generic `wrangler deploy` from the repository root: there is no root config, and the
two runtime directories are deliberately separate so a command cannot pick the wrong one.

## CI

`.github/workflows/ci.yml` job "TS Worker typecheck, parity tests and bundle" (no credentials,
`--dry-run` only) runs alongside the frontend and Python jobs; the Pages build waits for all of
them. Python evaluation and parity-freshness tests stay in the backend job.
