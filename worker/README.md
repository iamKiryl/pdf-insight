# PDF Insight API — compact TypeScript Worker (deployed backend)

Port of the reviewed Python compact path (`backend/src/pdf_insight`) to a thin TypeScript
Cloudflare Worker, to remove the Python Workers CPU overhead measured on Workers Free
(docs/STATUS.md). Same public API (`GET /api/health`, `POST /api/analyze`), same JSON errors,
same Workers AI binding and model, same rate-limit namespaces. Only the compact mode exists here;
the experimental single/chunked modes stay in Python. The Python implementation remains the
reference and the evaluation tooling.

## Setup and checks

```bash
cd worker
npm ci
npm run typecheck      # src (workers types) + tests (node types)
npm test               # parity with Python + transport/analysis behaviour (fake bindings)
npx wrangler deploy --dry-run --outdir dist   # bundle only, nothing uploaded
```

The result schema is the frontend's Zod contract (`frontend/src/lib/schema.ts`), resolved with
this package's `zod` (alias in `wrangler.jsonc`, `vitest.config.ts`, `paths` in `tsconfig.json`).

## Parity with Python

`backend/tools/parity_fixtures.py` runs the PYTHON code and writes golden files to
`test/parity/` (synthetic and adversarial texts, the synthetic offer, the exact prompt/schema);
`--sample` also writes the recruitment sample with the live run-J selection to the git-ignored
`.local/parity/sample.json`. `test/parity.test.ts` requires identical candidates (kind, page,
value, currency, date, exact context and order), the identical marked prompt, and per scenario
the identical assembled result or the same invalid-output problem paths. A backend test
(`tests/test_parity_fixtures.py`) fails if the committed golden files no longer match Python, so
they can only be regenerated from Python and reviewed. `src/prompt.ts` is generated from Python.

Covered: wrapped and ambiguous amounts, identifiers/percentages, currency after a line break,
long rows/sentences, multi-value sentences, source marker characters, table headers, flattened
tables, paragraph stops, invoice currency declaration, running footers and dedup, repeated body
events, prose crossed by a wrap, sentences below tables, initials, date formats and invalid dates,
prompt injection and fake tags, unknown/wrong-kind/repeated IDs, strict types (string IDs, number
as boolean, missing field, ignored extra fields), insufficient content, leaked markers, bad
language/type, empty title fallback, duplicate key points, attested/mixed/unrelated names,
organisation legal-form resolution, too many candidates, the offer and the 12-page sample.

### Known deviations from Python (none observed on the fixtures)

- `\d` is ASCII here; Python `re` also matches other Unicode decimal digits.
- Python lengths count code points; Zod `.max()` and the context bound count UTF-16 units. Request
  limits (page/total characters, file name) use code points as in Python; contexts differ only for
  text with characters outside the Basic Multilingual Plane.
- JSON numbers: `1.0` is accepted where Python strict mode would reject a float for an int field
  (JS cannot distinguish them). Python accepts `NaN`/`Infinity` tokens in request JSON; JS rejects
  them (INVALID_REQUEST).
- `casefold` is approximated by `toLowerCase` plus `ß → ss`.
- Unknown `AI_MODE` or model fails closed with `SERVICE_MISCONFIGURED` (Python falls back to
  `single` for an unknown mode). Only `@cf/meta/llama-3.3-70b-instruct-fp8-fast` is allowed.

## Local performance profile (not production CPU)

`profile/entry.ts` + `wrangler.profile.jsonc` (local only, never deployed) replay the full
`POST /api/analyze` path N times with a fake AI returning the run-J selection:

```bash
npx wrangler dev --config wrangler.profile.jsonc --port 8791
```

Results are in docs/STATUS.md. Local wall time is not Cloudflare CPU time; the AI binding,
network wait and the timeout path are not exercised.

## Deployment (NOT executed — after review only)

See docs/RUNTIME.md for the exact command, the replacement semantics and the rollback.
