# Handoff — PDF Insight, 2026-10-06 (≈ 13:45 Warsaw; deadline 14:44)

Facts for the submission decision. Nothing has been sent to the recruiter; submission is the
user's step.

## Links and exact revisions

| What | Value |
|---|---|
| Demo | https://iamkiryl.github.io/pdf-insight/ |
| Repository | https://github.com/iamKiryl/pdf-insight |
| Frontend (Pages) | commit `1b1ddd7`, deployed by CI run [37456785150](https://github.com/iamKiryl/pdf-insight/actions/runs/37456785150) (13:31) |
| Backend | Cloudflare Worker `pdf-insight-api` (TypeScript, compact, Llama 3.3 70B), version `7f5eed60-d76e-4595-9371-3c2de449c8b4` (app code `1fd7999`, 13:29), https://pdf-insight-api.pdf-insight-api.workers.dev |
| Last successful CI | run [37457195586](https://github.com/iamKiryl/pdf-insight/actions/runs/37457195586) on `c357017` (frontend, Python, TS Worker checks, build); this handoff commit runs CI again |
| Availability intent | 14 days, until 2026-10-20, on Cloudflare Workers Free + GitHub Pages; no paid plan, **no availability guarantee** |

## Requirements (docs/PLAN.md)

| ID | Priority | State |
|---|---|---|
| F-01 Upload (drag & drop / chooser, ≤ 10 MB) | MUST | done, verified on the public demo |
| F-02 Text extraction, pages without text | MUST | done, verified (12 pages, page 11 flagged) |
| F-03 3–5 sentence factual summary | MUST | done; content passed AI-assisted source review in public runs P and Q |
| F-04 Strict schema, one retry | MUST | done (Zod + strict model-output checks; correction path tested offline) |
| F-05 Readable result, JSON view/download | MUST | done, export identical to preview |
| F-06 Empty/loading/error/retry states | MUST | done |
| F-07 Public GitHub Pages demo | MUST | **live, but the < 30 s target is not reliably met** (below) |
| F-08 Long documents (chunking + merge) | SHOULD | **not done** — > 30 000 characters is rejected with a clear message, never truncated; Python chunked mode is an unaccepted experiment |
| F-09 Local history | SHOULD | done, verified on the public demo (reopen without a request) |
| F-10 OCR of scans | COULD | **published as optional browser OCR with manual correction**; OCR flow verified locally and publicly without AI; **OCR text → AI analysis not verified** |

## Measurements (12-page sample contract)

| Run | Where | Result | Time | Worker CPU |
|---|---|---|---|---|
| P | public demo, TS Worker `dd6a5db2` | accepted (71/71 + AI-assisted review) | **26.5 s** upload-to-render | 37 ms |
| Q | public demo, TS Worker `d7e5ae75` | 70/71 — only latency failed; content review pass | **30.7 s** (model call 30.2 s) | 39 ms |
| L | public demo, earlier Python Worker | **failed: AI timeout** at 40 s | 40 s | 303 ms |
| K | deployed Python Worker via local frontend | 71/71 + review | 25.3 s | not observed |

- Latency is dominated by the model call (25–30 s). < 30 s is met in some runs only.
- **CPU 37–39 ms per analysis exceeds the 10 ms documented for Workers Free** (non-AI requests
  0–6 ms). No resource-limit error was observed; sustained overruns may be enforced by Cloudflare.
- Workers AI free allocation is shared by all visitors (≈ 400 neurons per analysis, 10 000/day).
- Model alternatives: Gemma 4 passed the contract (18.5 s locally) but failed the offer (omitted
  a rejected bid) → stopped; Llama 3.1 8B variants unavailable/incompatible with JSON mode.

## AI and OCR limits

- Quality evidence covers two documents (the sample contract and a synthetic offer) with an
  automatic evaluator and AI-assisted (Claude) source reviews — **not a human review**. Runtime
  and schema tests prove structure and behaviour, **not semantic accuracy**, and do not prove
  sustained Free-plan availability.
- OCR (Tesseract.js in the browser) makes real errors on page 11: missing heading, `o.o.` → `0.0.`,
  `§` → `$` (which would create false USD amounts). They are fixed only if the user corrects the
  text against the page image in the review step. No model analysis of OCR text was run
  (final checkpoint was explicitly without AI calls).
- Tables are flattened row by row; amount lists are long because the model selects many candidates.

## Local setup and checks

See [README.md](../README.md#local-development): frontend `npm ci && npm run lint && npm run
format:check && npm run typecheck && npm test && npm run build`; Worker `npm ci && npm run
typecheck && npm test`; Python reference `uv sync && uv run pytest -q`. Latest counts: frontend 136,
TS Worker 174 (incl. 92 Python-parity), Python 459 tests.

## Rollback

1. Frontend first: run CI → Run workflow with `deploy` on a branch pointing at `54515a5`
   (previous Pages build, no OCR).
2. Worker: `cd worker && npx wrangler rollback d7e5ae75-a043-45c7-8f7f-2ecac09e9d74 --name
   pdf-insight-api` (previous TS; rejects `ocrPages`), or `dd6a5db2-…`; Python
   `a4695cc8-ac6c-47a9-9253-6facf931c2b9`. Details: [RUNTIME.md](RUNTIME.md), [OCR.md](OCR.md).

## Open items

1. **F-08 long documents** — unmet SHOULD (not cancelled, not counted complete).
2. Model latency around the 30 s target; CPU above the Free limit.
3. End-to-end verification of AI analysis on accepted OCR text.
