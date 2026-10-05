# AI assistance log

## 2026-10-05 — architecture and implementation handoff

- Tool: Codex. Read the recruitment brief and sample PDF, created and audited the plan (docs/PLAN.md).
- Human instruction: begin implementation with logical commits; use Codex mainly as architect/reviewer and Claude Opus through the signed-in work subscription for initial implementation, without additional spending.
- Codex inspected Claude Desktop: Code available, Opus selected, Fast mode off. Subscription usage showed 0%; a separate Usage credits budget was visible. Billing protection needs verification before unattended execution.
- Codex created repository handoff instructions in CLAUDE.md. No application code or live model validation exists at this checkpoint.

Append actual implementation prompts, relevant outputs, mistakes, corrections and checks as work occurs. Do not invent prior usage or successful tests.

## 2026-10-05 — Stage 1 implementation (Claude Code, Opus, signed-in subscription)

Tool: Claude Code desktop (Code tab), model Opus. No paid API credentials, no Fast mode, no
additional usage purchased, no other models delegated to.

### Prompts

1. Human → Claude (verbatim, Russian): «Прочитай CLAUDE.md и docs/PLAN.md. Выполни Stage 1 из
   CLAUDE.md: реализуй рабочий MVP, запусти проверки и сделай логические Conventional Commits.
   Обновляй AI_LOG.md по фактической работе. Используй только Opus через текущую подписку. Не
   подключай платные API, не включай Fast mode и не покупай дополнительный лимит. При исчерпании
   подписки остановись. Не публикуй проект. В конце запиши результаты проверок и оставшиеся
   проблемы в docs/STATUS.md и дай короткий отчёт для ревью Codex.»
2. Repository instructions: CLAUDE.md "Stage 1: executable vertical slice" (written by Codex).
3. Application prompt sent to Workers AI (designed in this session, not yet run live): system
   prompt in `backend/src/pdf_insight/prompt.py` — document is untrusted data, injection attempts
   must not be followed or reported as facts, no invented or summed amounts, main-body language,
   attachments do not change the type, title copied or null, 3–5 sentences ending with periods,
   `insufficientContent` instead of padding.
4. Retry prompt (one retry only): "Your previous answer did not pass validation: <field paths and
   messages>. Return a corrected JSON object…" — validation messages exclude input values.

### Actions

- Verified current Cloudflare docs (Python Workers, FastAPI, Workers AI binding, JSON mode, Rate
  Limiting binding, limits) and read the `workers-runtime-sdk` 1.9.2 source; recorded assumptions in
  docs/STATUS.md.
- Contracts first: request/response/error spec, ISO code lists (generated from pycountry 26.2.16,
  `XXX`/`XTS` removed), numeric limits, 3 accepted / 28 rejected output fixtures, sentence cases.
- Backend: FastAPI app separated from the Workers entrypoint so pytest runs on CPython; Workers
  adapters for AI and rate limiting; entrypoint body bound; tests for retry, provider failures,
  limits, origin, rate limiting, injection isolation, logs.
- Frontend: pdf.js extraction with line reconstruction, request limits, single-request client
  with Zod validation, flow hook with stale-response protection, result UI, Vitest suites.
- Ran the real Worker in local workerd/Pyodide without credentials (smoke config) and the UI in the
  in-app browser at 360 px. The sample contract PDF (outside the repository) was read locally for
  extraction checks only and is not committed; its text was treated as data.
- CI workflow (lint → typecheck/tests → build → manual Pages deploy), README, STATUS.

### Mistakes made by the AI and how they were caught

- Wrong expected value in a shared fixture (`ok. 30` is also an ambiguous boundary → max 5, not 4).
  Caught by pytest; fixture corrected after re-deriving the rule.
- Body precheck initially required `Content-Length`; real workerd returned `JsNull` for the missing
  header (500) and the dev proxy streamed large bodies chunked. Caught by the local workerd smoke
  test; replaced by a streamed `limit + 1` read in the entrypoint.
- First `worker.py` draft contained a leftover duplicate request construction; rewritten before
  any run.
- `ruff format .` reformatted pywrangler's generated `python_modules/`; deleted and excluded.
- Used pdf.js option `isEvalSupported`, removed in pdf.js 6; caught by `tsc`.
- Literal NBSP inside a regex; caught by ESLint `no-irregular-whitespace`.
- Test helper used `import.meta.url`, which is not a `file:` URL under jsdom; caught by Vitest.
- Tables had no accessible names; caught by a Testing Library query, captions added.

### Not done / not claimed

- No live Workers AI call, no deployment, no GitHub repository or Pages URL, no latency, CPU or
  quota measurements. Mocks and a local stub were used for model responses; they are not live AI
  verification.

## 2026-10-05 — Fixes for Codex review of Stage 1 (Claude Code, Opus, subscription)

Prompt (human → Claude, verbatim): «Codex проверил Stage 1. Прочитай docs/REVIEW_STAGE1.md и
выполни раздел Next Claude prompt: исправь два дефекта отдельными коммитами, добавь регрессионные
тесты, обнови STATUS и AI_LOG. Пока без деплоя и расширения функциональности.»

Both review findings were real defects in code written by Claude in Stage 1:

1. **Unbounded bodies (P1).** My entrypoint bounded only an exact `POST /api/analyze` and passed
   every other request straight to the Workers ASGI adapter, which queues the full body. I had
   verified the adapter behaviour myself and still only protected one route. Fix (`ccc0fa5`): the
   entrypoint now rebuilds every request; only `POST /api/analyze` (path percent-decoded like the
   adapter) reads up to limit+1 bytes, slicing chunks before retaining them; everything else is
   forwarded without a body; FastAPI `redirect_slashes=False`. New tests load `src/worker.py`
   with fake `js`/`workers`/`pyodide` modules and count stream reads; 10 of them fail on the old
   entrypoint. Local workerd: 20 MB chunked uploads to `/api/analyze/`, `/unknown`, PUT/PATCH →
   404/405 in ~4 ms with 0 bytes uploaded; `/api/analyze` → 413.
2. **Incomplete model output accepted (P1).** My `build_result` used `payload.get(key, [])`, so
   a model answer with missing keys became a 200 with empty collections and no retry. Reproduced
   the reviewer's case (200, one call) with a failing test first. Fix (`bd991ae`): strict raw
   `ModelOutput` (all 12 keys, strict types, only title/date nullable, extra keys ignored) is
   validated before normalisation; explicit `insufficientContent: true` still short-circuits.
   Tests: each missing key → exactly two calls then 200, twice → `AI_INVALID_OUTPUT`; 16 wrong
   shapes; explicit null/[] valid on the first call; requested JSON schema parity.

Mistakes during the fix: one new test passed `str` header keys where the callback receives
`bytes` (test corrected); a curl smoke loop used an unquoted zsh variable that was not
word-split, producing invalid-header 400s from the dev proxy (rerun with explicit arguments).

Checks after the fixes: backend ruff/format clean, pytest 161 passed; frontend lint, format,
typecheck clean, Vitest 81 passed, `/pdf-insight/` build with worker path check passed. No
deployment, no live AI, no paid APIs.

## 2026-10-05 — Live Workers AI checkpoint (Claude Code, Opus, subscription)

Prompt (human → Claude, verbatim): «Codex принял исправления. Прочитай раздел Re-review at
392fdd1 в docs/REVIEW_STAGE1.md и выполни следующий checkpoint: реальный Workers AI через локальный
pywrangler. Сначала помоги мне авторизоваться в Cloudflare и проверить бесплатный план. Никаких
платных подключений; секреты в чат не запрашивай. Проверь тестовый PDF: польское резюме, суммы и
даты, JSON, игнорирование инъекции на странице 4, предупреждение о странице 11, время ответа.
Максимум три полных анализа до следующего ревью. Результаты запиши в docs/LIVE_AI_RESULTS.md.
Пока без публикации. При необходимости моего действия дай точную инструкцию.»

Actions and blockers, in order:
- `wrangler whoami`: not authenticated. Gave the user `npx wrangler login` instructions; the first
  attempt (run through the chat's `!` input) timed out waiting for the OAuth callback; the user then
  logged in from a terminal. Claude never read or printed the stored credentials.
- The user confirmed Workers Free (active) and no payment method in Billing (screenshot).
- Added `618d798` (log model call and token usage counters) to measure neurons per analysis.
- Model catalog check without inference: Llama 3.3 70B fp8-fast, 24 000-token context.
- `pywrangler dev` failed: "You need to register a workers.dev subdomain before running the dev
  command in remote mode". The user registered the subdomain in the dashboard (account setting).
- Run 1 (committed 25 s timeout): 504 `AI_TIMEOUT`. Claude raised the per-attempt timeout to 60 s
  in the ignored local `.dev.vars` only, to measure real latency. Runs 2–3: 200 in ~30 s,
  identical results, 20/24 automated checks. Stopped at three analyses as instructed.

Observations about the model (not Claude's code): it kept the injection out and grounded all
amounts and dates, but omitted the gross amount and invoice/payment dates and dropped net/period
qualifiers and legal forms. Claude's own planning error surfaced here: the 25 s per-attempt default
chosen in Stage 1 was never measured and is too short for this document.
