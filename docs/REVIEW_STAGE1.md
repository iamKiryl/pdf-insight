# Codex review — 2026-10-05

Reviewed implementation at a7e8368. Independent checks: frontend lint, formatting, typecheck, 81 Vitest tests and production build with /pdf-insight/ base passed. Backend Ruff lint/format and 96 pytest tests passed. This is not live AI or deployed-demo validation.

## Required fixes before deployment

1. **P1 — unbounded requests reach the ASGI adapter.** `backend/src/worker.py:24` bounds only POST /api/analyze; POST /api/analyze/ (trailing slash), unknown paths and other methods go directly to asgi.fetch. The installed workers/asgi.py process_request queues the entire incoming body before running the application. Such requests bypass the application cap and can exhaust Worker memory even when eventually rejected or redirected. Bound all request bodies before the adapter, or reject unsupported routes/methods without consuming their bodies; explicitly handle trailing slash and preflight. Also slice incoming chunks before retaining them in read_limited (currently appends a whole chunk before truncation). Add meaningful tests and local workerd checks of unknown paths, trailing slash, unsupported methods and chunked oversize requests.

2. **P1 — incomplete model responses silently become successful analyses.** `backend/src/pdf_insight/analyzer.py:95-125` uses get/defaults before validating the model payload. Reproduction: take valid_model_output(), remove amounts, dates, organizations, people, keywords, date, title and insufficientContent; FakeAI returns it; POST responds 200, attempts=1, amounts=[]. Missing model keys are indistinguishable from explicitly empty results, and the required correction retry never happens. Validate required raw fields and their shapes before normalization; preserve supported explicit null title/date and [] semantics. Add tests for each missing field: one invalid then valid => exactly two calls; two invalid => AI_INVALID_OUTPUT. Keep server-owned metadata protection.

## Remaining delivery scope (not Stage 1 defects)

- F08 chunking, F09 local history and F10 OCR are not implemented. Next stage must implement actual chunk+merge, not merely increase limits; history must be bounded, clearable and store results only. Browser OCR is a possible no-backend-storage approach, but first decide language assets, performance and extraction strategy.
- Live Workers AI quality, injection resistance, amount/date accuracy, CPU, latency and quota remain untested. Two 25-second attempts can exceed the <30-second target; measure and decide a total deadline from evidence.
- GitHub Pages publication, backend origin/URL configuration, screenshot and 14-day availability remain pending.
- Multi-column extraction interleaves columns. Test meaning preservation on the supplied PDF before claiming robust extraction.

## Next Claude prompt

Read this review and CLAUDE.md. Fix findings 1 and 2 in separate logical fix commits, add regression tests, run all existing checks, and update AI_LOG.md and docs/STATUS.md with actual evidence. Do not publish, use paid APIs or change provider/language. Do not yet expand into F08-F10: return the reviewed core first. Report commit hashes, test results and any exact blocker. Codex will independently review the fixes before the live integration stage.
