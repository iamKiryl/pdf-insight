# PDF Insight API contract

Single source of truth for the request, response and error shapes shared by the
Python backend (Pydantic) and the TypeScript frontend (Zod). Both validators run
the same fixture files in `fixtures/`, so a schema change must update both sides
and the fixtures in one commit. Numeric limits live in `limits.json` and code lists in
`codes.json`; tests on both sides assert their constants match these files.

## `POST /api/analyze`

Request body (`Content-Type: application/json`, at most `MAX_BODY_BYTES`, default
262 144 bytes; the server stops reading the stream as soon as the limit is
exceeded):

```json
{
  "fileName": "umowa.pdf",
  "pageCount": 12,
  "pages": [{ "page": 1, "text": "..." }, { "page": 2, "text": "" }],
  "pagesWithoutText": [2]
}
```

Rules enforced by the server (browser metadata is untrusted):

| Field | Rule |
|---|---|
| `fileName` | 1–255 chars after trimming, no control characters or path separators |
| `pageCount` | integer 1–500 |
| `pages` | exactly `pageCount` items, `page` numbers `1..pageCount` in order, each `text` ≤ 20 000 chars |
| `pagesWithoutText` | exactly the pages whose text contains no Unicode letter, ascending |
| total text | ≤ 48 000 chars (model context budget). Longer documents are rejected with `DOCUMENT_TOO_LONG`; nothing is truncated silently (chunking, F-08, is not implemented yet) |
| content | every page without text → `NO_TEXT_LAYER`; fewer than 200 letters in total → `INSUFFICIENT_CONTENT` (no AI call) |

The response `document.fileName` and `document.pages` are copied from the
validated request; the model never produces them.

## Response (200)

All brief keys are required. `analysis` is a documented extension added by this
project (the brief allows additional keys); it is optional in the schema so a
brief-only object still validates, but the API always sends it.

```json
{
  "document": { "fileName": "string", "pages": 12, "language": "pl", "type": "umowa", "title": "string", "date": "2026-03-12" },
  "summary": "3–5 sentences in the document language.",
  "keyPoints": ["3–7 items"],
  "entities": { "organizations": [], "people": [] },
  "amounts": [{ "value": 184500, "currency": "PLN", "context": "string" }],
  "dates": [{ "date": "2026-03-12", "context": "string" }],
  "keywords": [],
  "analysis": { "complete": false, "pagesWithoutText": [11], "titleFallback": false }
}
```

| Field | Rule |
|---|---|
| strings | every string fact is non-empty after trimming; no empty strings in arrays |
| `document.pages` | positive integer |
| `document.language` | lowercase ISO 639-1 code from `codes.json` |
| `document.type` | `faktura` \| `umowa` \| `oferta` \| `raport` \| `inne` |
| `document.title` | non-empty; when the document has no identifiable title the server sets a deterministic neutral label in the document language (`Dokument bez tytułu`, `Untitled document`, …) and `analysis.titleFallback = true` |
| `document.date`, `dates[].date` | calendar-valid ISO 8601 date `YYYY-MM-DD`; `document.date` may be `null` but the key is required |
| `summary` | 3–5 sentences (see below), ≤ 2 000 chars |
| `keyPoints` | 3–7 items |
| `entities.*`, `amounts`, `dates`, `keywords` | arrays, `[]` when absent; `keywords` ≤ 20 |
| `amounts[].value` | finite JSON number (not string/boolean) |
| `amounts[].currency` | uppercase ISO 4217 code from `codes.json` (`XXX`, `XTS` excluded) |
| `analysis.pagesWithoutText` | ascending, unique, within `1..pages`; `complete` is `true` iff the list is empty |
| unknown keys | rejected at every level, so the two validators cannot drift silently |

### Sentence counting

Naive splitting on `.` breaks on `sp. z o.o.`, `S.A.`, `1.5`, `12.03.2026 r.` and
initials. Both validators implement the same conservative interval:

1. A boundary candidate is a run of `.`, `!`, `?`, `…`, optionally followed by
   closing quotes/brackets, then whitespace, then optional opening quotes/brackets,
   then an uppercase letter or a digit. Anything else (lowercase next word,
   decimal point, no whitespace) is not a boundary.
2. The candidate is **ambiguous** when the next character is a digit, or when the
   run is a single `.` and the preceding token is a single letter, contains an
   internal dot (`o.o`, `m.in`), or is a listed abbreviation (`sp`, `nr`, `r`,
   `tj`, `ok`, `ul`, `np`, …). Otherwise it is **definite**.
3. `min = definite + 1`, `max = definite + ambiguous + 1` (0 for blank text).
4. A summary is valid when it ends with terminal punctuation and the interval
   `[min, max]` intersects `[3, 5]`.

The interval accepts every plausible reading instead of guessing; it is a
structural check, not proof that the sentences are true. Shared cases live in
`fixtures/sentences.json`.

### Insufficient content

The model may report that the text does not contain enough facts for 3 key
points and a 3-sentence summary. The server then returns `INSUFFICIENT_CONTENT`
instead of inventing content.

## Errors

```json
{ "error": { "code": "RATE_LIMITED", "message": "Polish user-facing text", "retryable": true } }
```

| HTTP | code | meaning |
|---|---|---|
| 400 | `INVALID_REQUEST` | malformed JSON or contract violation |
| 403 | `ORIGIN_NOT_ALLOWED` | browser `Origin` not in `ALLOWED_ORIGINS` |
| 413 | `BODY_TOO_LARGE` | body exceeded `MAX_BODY_BYTES` |
| 413 | `DOCUMENT_TOO_LONG` | text exceeds the model budget |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | not `application/json` |
| 422 | `NO_TEXT_LAYER` | no page has extractable text (scan without OCR) |
| 422 | `INSUFFICIENT_CONTENT` | not enough facts for a valid result |
| 429 | `RATE_LIMITED` | per-client or global limit reached |
| 502 | `AI_INVALID_OUTPUT` | model output failed validation twice (one retry) |
| 502 | `AI_UNAVAILABLE` | provider error |
| 503 | `AI_QUOTA_EXCEEDED` | Workers AI allocation exhausted |
| 503 | `SERVICE_MISCONFIGURED` | production config missing (for example the rate-limit binding); fails closed |
| 504 | `AI_TIMEOUT` | model call exceeded `AI_TIMEOUT_SECONDS` |

## `GET /api/health`

`{"status": "ok", "environment": "production" | "development", "aiBinding": bool, "rateLimiter": bool}`.
Does not call the model.
