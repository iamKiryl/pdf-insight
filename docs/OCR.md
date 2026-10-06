# Optional browser OCR (F-10) — 2026-10-06, NOT published

Implemented for review per docs/NEXT_BROWSER_OCR.md. Nothing was deployed: the public frontend
(`54515a5`) and the TS Worker (`d7e5ae75`) are unchanged. No Workers AI call was made.

## Flow

1. Text extraction as before. If pages have no text layer, the ready panel (partial scan) or the
   "Brak tekstu do analizy" error (fully scanned PDF) offers **Rozpoznaj tekst ze skanów (OCR)**.
   The normal text-only path is unchanged: "Analizuj z AI" sends exactly the old payload.
2. On that explicit click only: pdf.js renders **only the pages without text**, one at a time, to
   a canvas; Tesseract.js 7.0.0 (one Web Worker, `pol` + `eng`, LSTM) recognises them. Progress
   and **Anuluj OCR** are shown; cancel terminates the worker and the pdf.js task at once.
3. Review panel: recognised text per page (confidence shown as an indicator only), a warning that
   amounts/names/dates can be misread, pages with no recognised letters listed as staying
   unanalysed. **Użyj rozpoznanego tekstu** or **Odrzuć OCR** (back to the previous panel,
   unchanged). Nothing is sent to the API when OCR finishes.
4. After acceptance the ready panel shows the OCR provenance warning; the request gets
   `ocrPages`, `pagesWithoutText` is recomputed from the accepted text (unrecovered pages stay
   flagged), existing per-page/total character and body limits apply (no truncation).
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
| Concurrency | sequential, one worker; canvases zeroed and pages cleaned after each page; worker and PDF task released on success, failure, cancel, reset, new file and unmount (run id + AbortController) |
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
amounts and dates. The model would see them marked as OCR text but could still select them. No
OCR-specific rewriting was added (it would be a document-specific heuristic); the user sees the
text before accepting. This is the main open risk of the feature and is unverified with the model.

The cancellation race was exercised in the real browser (start → cancel after 300 ms → previous
panel, no stale review after 1.5 s) and in unit tests. Desktop and 360 px screenshots of the
synthetic document: `docs/screenshots/ocr-*.png`; sample screenshots and texts stay in `.local/`.

## Deployment order (when approved)

The deployed Worker `d7e5ae75` rejects the new `ocrPages` field (strict schema). Deploy the Worker
first, then Pages; otherwise OCR analyses fail with INVALID_REQUEST (the text-only path is
unaffected either way). Python is the reference: experimental single/chunked modes reject
`ocrPages` (they cannot mark OCR text).

## Limitations

- OCR quality depends on the scan; Tesseract misreads symbols (`§` → `$`, `o` → `0`) and may drop
  large headings. Confidence is not accuracy. No manual text editing in the review step.
- Not tested: handwriting, rotated or low-resolution scans, very large page images, Safari/Firefox,
  low-memory phones, the 90 s timeout against a real slow page (unit-tested with fake timers).
- Not measured on GitHub Pages bandwidth; first OCR downloads ≈ 9.6 MB (more on a slow link).
- The model's handling of OCR-marked text (including the false `$` candidates) is not evaluated:
  no AI call was allowed in this checkpoint.
