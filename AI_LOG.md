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

## 2026-10-05 — AI tuning checkpoint (Claude Code, Opus, subscription)

Prompt (human → Claude, verbatim): «Codex проверил живые результаты. Выполни
docs/NEXT_AI_TUNING.md. Разрешено сравнение моделей внутри текущего Cloudflare Free. Максимум 6
фактических вызовов модели, включая корректирующие повторы. Не сокращай полноту данных ради
скорости и не подгоняй код под тестовый PDF. Без платных подключений и публикации. Обнови
результаты, STATUS и AI_LOG, сделай логические коммиты.»

What Claude did:
- Observability (`a9c9560`): started vs completed model calls, usage-known flag, model id in logs.
- Overall deadline and model profiles (`2e0f17f`): 55 s request budget, ≤ 40 s per call, retry
  only with ≥ 5 s left, 65 s browser timeout; Workers-style vs OpenAI-style request/response per
  model, unknown model fails closed.
- Prompt v2 (`6ad12b9`): generic completeness rules; evaluator package with atomic checks and a
  synthetic Polish offer (`9a4982e`).
- Model availability checked in the account catalog before any call: the reviewer's
  `@cf/meta/llama-3.1-8b-instruct` was absent; chose Gemma 4 26B-A4B (schema-confirmed
  json_schema, 256k context) and recorded why the fp8 Llama 3.1 variant was not used.
- Five live calls: 70B sample ×2 (30/45), 70B synthetic offer (51/53), Gemma sample (truncated at
  2 048 tokens, retry stopped by the deadline). Stopped at five because one more analysis could
  have needed two calls and exceeded the limit of six.

Mistakes / issues found:
- Claude's first prompt-v2 edit script turned backslash line continuations into one very long
  line (Python string escape inside a heredoc); caught by ruff E501 and rewritten.
- `run_live.py` read the worker log before wrangler flushed the line (serverLog null on run A);
  fixed in `b44b03a`, run A's metadata patched from the log afterwards.
- Model-side: the 70B under-extracts on the 12-page document despite explicit instructions and
  once produced corrupted Polish characters on the offer; Gemma produced an overlong answer.
- Claude's earlier assumption that latency would follow output length is not supported: ~30 s
  appeared for 622–917 output tokens and 1.8k–9.4k input tokens alike.

## 2026-10-05 — Evaluator audit fixes (Claude Code, Opus, subscription; offline only)

Prompt (human → Claude, verbatim): «Прочитай docs/REVIEW_EVALUATION.md и выполни Next Claude task.
Сначала воспроизведи дефекты тестами, затем исправь оценщик. Повторно оцени сохранённые ответы без
вызовов AI. Не считай непроверенный смысл резюме и контекстов успешной проверкой. Пока без
chunking, новых живых запросов и публикации.»

- Reproduced all six audit findings as failing tests against the evaluator Claude had written
  (`amount_in_source` substring/decimal bugs, wrong date events, keyword-soup contexts, wrong file
  name, unjudged nonsense summary). Output saved in `.local/live/eval-regressions-before-fix.txt`.
- Rewrote the evaluator as v3 (`6ccc699`): bounded number/date parsing with currency association,
  page+snippet evidence per expected fact (validated, nothing from page 11), qualifiers and events
  judged on one entry, contradiction/negation checks, schema/metadata/coverage checks, manual
  dimensions with an evidence table and SHA-256-bound review files, statuses and `--check` exit
  codes (tested against a fake local server, no AI). Added a hand-written reference answer and a
  labelled adversarial fixture. Offline rescoring tool (`aaadd61`).
- Mistakes found on the way: the first event check let "Nieprawdziwa data rozpoczęcia
  zatrudnienia" match "work start" (fixed by requiring all event groups); the parser counted a
  zero-padded KRS number as an amount (identifiers skipped); while rescoring, the negation pattern
  matched the Polish preposition "na" (`dc495b7`). The file-writing tool turned ` ` escapes
  into literal NBSP characters in regexes (caught by ruff RUF001, restored as escapes). A
  placeholder commit hash briefly appeared in the results doc before being corrected.
- Re-scored all seven saved responses offline: every one is `failed`; no manual review was done,
  so no summary or context meaning is counted as passed. No model calls, chunking or publication.

## 2026-10-05 — Codex evaluator re-review

Reviewed 7fbae0e and independently repeated numeric, wrong-event and fabricated-summary probes. Observed corrected rejection/pending statuses. Ruff lint/format passed. Initial pytest: 232 passed, 5 errors from sandbox-denied localhost socket binding. After network permission for local test servers, full pytest: 237 passed. No provider calls. Next implementation task recorded in docs/NEXT_CHUNKING.md; mock results will not justify changing production default.

## 2026-10-05 — Chunked extraction (F-08) implementation (Claude Code, Opus, subscription; no live AI)

Prompt (human → Claude, verbatim): «Codex принял исправления оценщика. Выполни docs/NEXT_CHUNKING.md:
реализуй извлечение по частям и безопасное объединение фактов, с ограничением параллельности,
общего времени и повторов. На этом этапе без живых AI-вызовов и публикации. Не меняй основной
режим на основании тестов с заглушками. Обнови документацию, запусти проверки и сделай логические
коммиты.»

Commits: `2130324` parser moved to `pdf_insight.numbers` (runtime grounding needs it), `9721ba0`
chunk builder, `00714a2` typed chunk outputs + grounding + merge, `31c36c2` opt-in orchestration
(`AI_MODE=chunked`), `42def19` frontend limit/message, plus this documentation commit.

Decisions: parallel overview call (full text or digest of every page) instead of a sequential
summary; ≤ 2 calls in flight; one overall deadline; one retry per request; any failure cancels the
rest and fails the request; ungrounded facts dropped and counted; equal values never merged across
meaning; request envelope 64 000 chars with a proven chunk bound; default stays single-call.

Checks: tests use scripted provider responses only. Mutation check: raising the retry budget to 5
or the concurrency to 5 made the corresponding tests fail, then the code was restored.

Mistakes on the way: a chunking test assumed a paragraph break outside the boundary window would be
used (the documented rule is the last 1 000 chars) and then exceeded the 20 000-char page limit;
first drafts of `chunk_prompt.py` and `merge.py` contained dead code and stray try/except/imports,
removed before committing; the file tool again turned ` ` escapes into literal characters
(rewritten as escapes); the worst-case quota estimate was first understated (retry input) and
corrected to ≈ 5 600 neurons; a temporary backup during the mutation check was written to /tmp
instead of the scratchpad and deleted afterwards.

Known risk recorded for review: with ~30 s per 70B call, the sample's 4 calls in two rounds likely
exceed the 55 s budget. Nothing here is live-verified.

## 2026-10-05 — Chunking review fixes (Claude Code, Opus, subscription; no live AI)

Prompt (human → Claude, verbatim): «Прочитай docs/REVIEW_CHUNKING.md. Исправь только перечисленные
дефекты, сначала добавив воспроизводящие их регрессионные тесты. Не увеличивай общий бюджет
повторных вызовов. Сохрани AI_MODE=single по умолчанию. Без живых AI-вызовов и новых функций.
Запусти проверки, обнови STATUS и AI_LOG, сделай отдельные fix-коммиты.»

- Wrote 20 regression tests first (`test_merge_identity.py`, `test_evidence_support.py`,
  `test_evidence_rejection.py`); 16 failed on the reviewed code, reproducing every finding.
- `63b22b1`: merge identity requires identical meaning AND the same source occurrence; evidence is
  located in the chunk's own segments with exact raw offsets (`normalize_with_map`); organisation
  alias limited to "name + legal form".
- `d284d52`: unsupported evidence raises InvalidModelOutput inside each chunk call's validation
  (shared single retry), unresolved → AI_INVALID_OUTPUT; `droppedFacts` removed.
- `0a80133`: amount tokens are taken from the cited occurrence (token offsets added to the parser);
  currency must be stated there (marker or page "Waluta:" line); claimed qualifiers must be named
  in the same sentence/table row (±200 chars).
- Mistakes on the way: one new test first placed both repeated snippets inside the same chunk (the
  layout was corrected, then it still failed on the old code as intended); earlier test fixtures
  had claimed "one-off"/"monthly" periods the source did not state — exactly what the new rule
  rejects — and their expected contexts contained the unsupported "jednorazowo" label; the
  fixtures were corrected rather than the rule weakened. Two earlier merge tests encoded the
  overlap-means-identical rule the review identified as a defect and were updated.
- The sentence window is a heuristic; it can reject legitimate facts (e.g. qualifiers beyond an
  abbreviation like "sp. z o.o."). That trade-off is documented and untested on real output.

## 2026-10-05 — Chunked-mode live trial (Claude Code, Opus, subscription)

Prompt (human → Claude, verbatim): «Codex принял исправления. Выполни следующий checkpoint из раздела
Re-review of 06f389b в docs/REVIEW_CHUNKING.md. Один анализ тестового договора с AI_MODE=chunked:
максимум 5 фактических вызовов модели, включая коррекцию. Сохрани текущие ограничения времени и
параллельности. Без автоматических повторных экспериментов и публикации. Проверь результат
оценщиком и вручную по исходному документу. При неудаче зафиксируй точную причину, не ослабляй
проверки. Обнови LIVE_AI_RESULTS, STATUS и AI_LOG.»

- Added per-call `model_call` log events (`ed4b255`) because the checkpoint required per-call
  label/timing/tokens/finish reason/validation reasons; tested that no source text is logged.
- Checked quota by own accounting (dashboard not read) and the call plan offline (3 chunks +
  overview, ≤ 5 calls) before calling; local `.dev.vars` override `AI_MODE=chunked`, restored
  afterwards; limits unchanged.
- Ran exactly one analysis: `AI_TIMEOUT` after 40.0 s. Overview ok (20.3 s, 8 934 / 437 tokens);
  chunk 1 hit the 40 s per-call cap; chunks 2 and 3 cancelled; 4 calls started, 1 completed. No
  result, so the evaluator reports `failed` and there was nothing to review manually. No repeat.
- Claude's earlier claim that 70B latency was ~30 s "regardless of size" was wrong: with this
  data point throughput is ~20–29 output tokens/s, so long, evidence-rich chunk answers are slow.
- New defect found in Claude's orchestration: a queued call was dispatched (3 ms) after the failure
  released its semaphore slot. Recorded, not fixed (checkpoint scope).

## 2026-10-06 — Compact candidate-selection checkpoint (Claude Code, Opus, subscription)

Prompt (human → Claude, verbatim): «Выполни docs/ADR_COMPACT_ANALYSIS.md. Сначала исправь гонку
отмены отдельным коммитом. Затем реализуй компактный режим: извлечение кандидатов кодом, выбор
идентификаторов моделью, сборка фактов из исходных цитат. После тестов — один живой прогон
договора. Только если качество и скорость проходят — прогон второго документа. Общий предел:
4 вызова модели, включая коррекции. Без платных подключений и публикации. Обнови результаты и
документацию. При неудаче остановись с точной причиной, не ослабляй критерии.»

- `1b929d6`: terminal-failure latch for chunked mode; event-controlled tests (3 of 5 failed before).
  One older test had only passed because queued calls were dispatched and then cancelled.
- `82bb960`: compact mode. While probing contexts offline Claude found and fixed its own context
  rules before any live call: PDF line breaks inside sentences had cut "odrzucono" from the 310 000
  context; "tj. " ended sentences; prose lines with two amounts were treated as table rows; headers
  were taken from prose fragments; "HARMONOGRAM I …" was not a heading. Two compact tests were wrong
  (a table without currency, a limit test without AI binding) and were corrected.
- Offline oracle check (no AI): with exactly the expected IDs selected, 5 sample checks and 1 offer
  check still fail (source sentences state net/VAT/gross together; a date line names no event).
- Live: one sample call, 200 in 22.6 s, evaluator failed 61/69, manual review (by Claude, labelled
  as AI) failed contexts: a wrong "200 PLN" produced by Claude's candidate parser from
  "295\n200,00" split across lines, footer dates selected, legal forms dropped. Stopped: the
  synthetic offer was not run; nothing was tuned after the call.
