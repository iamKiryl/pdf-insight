# Backend runtime

## Current state (2026-10-06, 12:20 Warsaw)

| | TypeScript Worker `worker/` | Python Worker `backend/` |
|---|---|---|
| Status | **deployed** as `pdf-insight-api`, version `d7e5ae75-a043-45c7-8f7f-2ecac09e9d74` (12:15 Warsaw, app code `17593aa`); previous TS version `dd6a5db2-5c7d-4b1f-b037-b8608459087e` (app code `191a1d8`) | previous production version `a4695cc8-ac6c-47a9-9253-6facf931c2b9` (from `c775866`), kept for exact rollback; reference implementation and evaluation tooling |
| Modes | compact only | compact, single, chunked (experiments) |
| Bundle / reported startup | 1 077 KiB / 149 KiB gzip, 30 ms | 8 985 KiB / 2 234 KiB gzip, 2 325 ms |
| Cloudflare CPU, health | 0–1 ms | 6–18 ms |
| Cloudflare CPU, full-size invalid request (no AI) | 5 ms (two requests) | 16 / 29 / 49 ms |
| Cloudflare CPU, sample analysis | **37 ms** (P, `dd6a5db2`), **39 ms** (Q, `d7e5ae75`); both the first analysis after a deploy | 303 ms (public run L, AI timeout) |
| Local workerd, warm full request (fake AI) | ≈ 4.2 ms | pipeline only 23.5 ms |

CPU values come from `wrangler tail` (one event each; cold/warm isolate state not controlled).
The Free plan documents 10 ms CPU per request and tolerates occasional overruns: the TS analysis
(37 ms) is far below Python but **still above 10 ms**; no resource-limit error was observed.

## Deploy (TS, the current runtime)

```bash
cd worker
npm ci && npm run typecheck && npm test
npx wrangler deploy --config wrangler.jsonc     # pdf-insight-api, same bindings and model
```

Verify without AI: `GET /api/health`, Pages preflight 204, foreign origin 403, and
`npx wrangler tail pdf-insight-api --format json` for `scriptVersion` and the `"runtime":"ts"`
log field (health looks identical for both runtimes).

## Rollback

- **Exact previous versions:** previous TS
  `cd worker && npx wrangler rollback dd6a5db2-5c7d-4b1f-b037-b8608459087e --name pdf-insight-api`;
  Python `... rollback a4695cc8-ac6c-47a9-9253-6facf931c2b9 --name pdf-insight-api`. A rollback
  restores the recorded deployment byte for byte (its bindings and vars included).
- `cd backend && uv run pywrangler deploy` deploys the **current** Python code and config from the
  working tree — not the old exact version. Use it only for a deliberate Python release.
- There is no root Wrangler config: run deploy commands only inside `worker/` or `backend/`; the
  local profiling configs (`wrangler.profile.jsonc`) must never be deployed.

## CI

`.github/workflows/ci.yml` runs frontend, Python and TS Worker checks (TS: typecheck, 103 tests
with fake bindings and Python golden parity files, `--dry-run` bundle). Deployment of the Worker
is manual (above); Pages deploys from the workflow dispatch with `deploy=true`.
