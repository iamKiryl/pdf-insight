# Optional browser OCR (F-10) — 2026-10-06, published 13:31 Warsaw

Implemented per docs/NEXT_BROWSER_OCR.md, fixed per docs/REVIEW_OCR_FIXES.md (`1b1ddd7`), then
published: TS Worker `7f5eed60-d76e-4595-9371-3c2de449c8b4` first, GitHub Pages from `1b1ddd7`
second (see "Publication" below). No Workers AI call was made in either checkpoint: **the model's
handling of OCR-marked text is not verified end to end.** F-10 is locally source-checked OCR with
user correction, not automatically verified fact extraction.

## Flow

1. Text extraction as before. If pages have no text layer, the ready panel (partial scan) or the
   "Brak tekstu do analizy" error (fully scanned PDF) offers **Rozpoznaj tekst ze skanów (OCR)**.
   The normal text-only path is unchanged: "Analizuj z AI" sends exactly the old payload.
2. On that explicit click only: pdf.js renders **only the pages without text**, one at a time, to
   a canvas; Tesseract.js 7.0.0 (one Web Worker, `pol` + `eng`, LSTM) recognises them. Progress
   and **Anuluj OCR** are shown; cancel terminates the worker and the pdf.js task at once.
3. Review panel ("Sprawdź i popraw rozpoznany tekst"): every recognised page — also one where OCR
   found no text — is an editable, labelled textarea next to the locally rendered page image
   (object URL, revoked on unmount; open in full size). The machine text is kept for
   **Przywróć tekst rozpoznany przez OCR**; an edited page says "Poprawiono ręcznie" instead of the
   machine confidence. Nothing is replaced automatically. Edits recompute missing pages, character
   counts and limits. **Użyj tego tekstu** or **Odrzuć OCR** (restores the pre-OCR document).
   Nothing is sent to the API when OCR finishes.
4. After acceptance the ready panel shows the OCR provenance warning; the request gets
   `ocrPages`, `pagesWithoutText` is recomputed from the accepted text (unrecovered pages stay
   flagged), existing per-page/total character and body limits apply (no truncation). OCR stays
   offered for remaining scanned pages; provenance is the **union** of all accepted passes (an
   empty or failed pass never removes it; text-layer pages never become OCR pages).
5. The backend marks those pages `<page number="N" source="ocr">` and adds one coverage sentence
   ("recognised by OCR in the user's browser and may contain recognition errors"); the result gets
   `analysis.ocrPages`, shown as a warning on the result and kept in JSON export and history.
   Without OCR the prompt, result and logs are byte-identical to before (all existing parity
   goldens unchanged; one new Python-generated `ocr-page` golden). The analyse log gets only the
   count `ocrPages`.

## Bounds (actual values, `frontend/src/lib/ocr.ts`)

| Bound | Value |
|---|---|
| Pages per OCR run | ≤ 20 (only pages without a text layer; more → explicit message) |
| Render | scale 2 (≈ 144 dpi), lowered so a page stays ≤ 4 000 000 pixels |
| Time | ≤ 90 s per step (PDF open, engine start, each page render/recognition); exceeded → run stops with a message |
| Concurrency | sequential, one worker; canvases zeroed and pages cleaned after each page (also for a render that completes after a timeout/cancel); PDF loading receives an abort signal (pdf.js task destroyed before it resolves); run rejected at once on cancel/timeout; stale results ignored via run id |
| Known limit | Tesseract.js cannot cancel a worker that is still starting: it is terminated when its start settles; if it never settles it lives until the page is closed |
| Text | existing limits after OCR: 20 000 chars/page, compact 30 000 total, 256 KiB body |

## Assets and privacy

Worker, three LSTM WASM cores (one is chosen by feature detection) and `pol`/`eng` `4.0.0_best_int`
language data are copied from pinned packages (`tesseract.js` 7.0.0, `tesseract.js-core` 7.0.0,
`@tesseract.js-data/pol|eng` 1.0.0) into `public/ocr/` at dev/build time
(`scripts/copy-ocr-assets.mjs`, git-ignored output) and served from this site under the Pages base
path; `cacheMethod: 'none'` (no IndexedDB copy). No third-party host is contacted: verified with the
CDP network log (no non-local request, no API request) in dev and in a production build served
under `/pdf-insight/`. Page images stay in browser memory.

Build impact: main chunk 342 → 354 KB (OCR UI/flow); Tesseract.js wrapper is a separate lazy chunk
(17 KB); `dist/ocr` adds 18 MB to the Pages artifact, of which a browser downloads ≈ 9.6 MB on the
first OCR (worker 0.1 MB, one core 3.9 MB, Polish 2.6 MB, English 2.9 MB; less with transfer
compression). The text-only path made **0** OCR requests (checked for both documents).

## Real OCR checks (local, headless Chrome, Apple Silicon)

| Document | Pages OCR'd | Time | Result |
|---|---|---|---|
| Synthetic image-only PDF (`frontend/fixtures/ocr/synthetic-scan-pl.pdf`, expected text beside it) | 1 (all) | 0.5–0.6 s with assets cached | 332 chars, confidence 95. **One error:** `sp. z o.o.` → `sp. z 0.0.`. Amounts (48 750,00 / 11 212,50 / 59 962,50 zł, 23%), dates (15 maja 2026, 30 czerwca 2026), names with diacritics (Łukasz Grzegorczyk, Zofia Wąsowska-Kęcka, Żuraw) exact |
| Recruitment sample, page 11 (scanned annex) | 1 of 12 | 0.9 s cold (incl. 9.6 MB asset download from localhost) | 683 chars, confidence 92; characters 20 701 → 21 384; partial warning replaced by the OCR warning. Correct: both amounts (12 300,00 → 13 100,00 PLN netto), all four dates, 120 → 135 users, signatories. **Errors:** the large heading "ANEKS NR 1" is **missing**; `sp. z o.o.` → `sp. z 0.0.`; `§` read as `$` three times; the stamp becomes noise ("KWADRAO \| Ear gorTWAF! wrocław") |

Consequence found offline (candidate extraction on the accepted text, no AI): the misread `$ 5`,
`$ 2`, `$ 3` become three **false USD amount candidates** (5, 2, 3 USD) next to the correct PLN
amounts and dates. No automatic rewriting was added; instead the review step lets the user
correct the text (below).

## Machine errors vs user corrections (after REVIEW_OCR_FIXES)

Machine output was byte-identical in every run (local dev, local build, public Pages). The user
edits below were made by Claude acting as the user, by comparing the text with the page image
shown in the review panel; they are **corrections, not recognition quality**.

| Page 11 | Machine OCR | User correction (from the page image) |
|---|---|---|
| Heading | missing | `ANEKS NR 1` inserted after `Załącznik nr 5` |
| Legal form | `sp. z 0.0.` | `sp. z o.o.` |
| Section signs | `$ 5`, `$ 2.`, `$ 3.` | `§ 5`, `§ 2.`, `§ 3.` |
| Stamp | `KWADRAO \| Ear gorTWAF! wrocław` | `KWADRAT SOFTWARE S.A. Wrocław` |
| Everything else | correct (amounts, 4 dates, 120 → 135, signatories) | unchanged |

683 → 693 characters; the corrected text was source-checked line by line against the image
(two-column signature block stays flattened as "Zamawiający Wykonawca / A. Kowalczyk P.
Dąbrowski"). Offline candidate extraction (Python reference, no AI) on page 11:

| Text | Amount candidates | Date candidates |
|---|---|---|
| Machine | 12 300,00 PLN, 13 100,00 PLN, **5 USD, 2 USD, 3 USD (false)** | 2026-03-12, 2026-03-20, 2027-03-31, 2027-04-01 |
| User-corrected | 12 300,00 PLN, 13 100,00 PLN | same four dates |
| Control: unedited OCR page "Opłata … wynosi $ 5 netto." | 5 USD kept (real dollar amounts survive) | — |

Synthetic scan: the only machine error (`sp. z 0.0.`) corrected by the user → text equals the
committed expected text exactly.

The cancellation race was exercised in the real browser (start → cancel after 300 ms → previous
panel, no stale review after 1.5 s) and in unit tests. Desktop and 360 px screenshots of the
synthetic document: `docs/screenshots/ocr-*.png`; sample screenshots and texts stay in `.local/`.

## Publication (2026-10-06)

1. Probe before deploy (no AI): request with `ocrPages` and too little text → old Worker
   `d7e5ae75` answered 400 INVALID_REQUEST (unknown field).
2. Worker deployed 13:29 Warsaw: version **`7f5eed60-d76e-4595-9371-3c2de449c8b4`** (same config,
   bindings and 70B model, 1 080 KiB / 150 KiB gzip). Without AI: health 200, preflight 204,
   foreign origin 403, the same probe → 422 INSUFFICIENT_CONTENT (field accepted, stopped before
   AI), invalid `ocrPages` → 400; tail: scriptVersion `7f5eed60`, `runtime: ts`, 0 model calls,
   CPU 0–6 ms.
3. Pages deployed from `1b1ddd7` (CI run 37456785150, all checks green). Public check without
   AI (headless Chrome, CDP network log): OCR assets 200 from `/pdf-insight/ocr/` (≈ 7.1 MB
   transferred on first use), cold OCR 2.2 s (synthetic) / 1.3 s (page 11), preview, edit, reset
   control, accept and provenance warning work; 0 API requests, no third-party host; machine and
   corrected texts identical to the local runs.

Rollback: frontend first (run the CI dispatch with deploy on a branch pointing at `54515a5`, the
previous public frontend), then the Worker
(`cd worker && npx wrangler rollback d7e5ae75-a043-45c7-8f7f-2ecac09e9d74 --name pdf-insight-api`).
The old frontend works with the new Worker (`ocrPages` is optional); the new frontend with the old
Worker fails only for OCR analyses (400). Python is the reference: experimental single/chunked
modes reject `ocrPages`.

## Limitations

- OCR quality depends on the scan; Tesseract misreads symbols (`§` → `$`, `o` → `0`) and may drop
  large headings. Confidence is not accuracy. Correction is manual: a user who does not compare
  with the image can still accept wrong text (false `$` amounts included).
- Not tested: handwriting, rotated or low-resolution scans, very large page images, Safari/Firefox,
  low-memory phones, the 90 s timeout against a real slow page (unit-tested with fake timers).
- Not measured on GitHub Pages bandwidth; first OCR downloads ≈ 9.6 MB (more on a slow link).
- The model's handling of OCR-marked text is not evaluated end to end: no AI call was allowed in
  either OCR checkpoint.
