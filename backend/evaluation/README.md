# Live-quality evaluation

Offline, atomic checks for real model outputs. Nothing here calls the model; `run_live.py` sends
one request to a **locally running** Worker (`uv run pywrangler dev`), which may call the model up
to twice (first call + one corrective retry).

- `checks.py` — one check per expected fact or qualifier: document fields, page coverage,
  organisations with legal forms, every expected amount and each stated qualifier
  (net/gross/VAT/period/status), every dated event, injection markers, and grounding (every amount
  and date in the result must occur in the source text, so invented or summed values fail).
- `cases/synthetic_offer_pl.json` — synthetic Polish offer (in the repository) with different
  amounts/dates than the sample, an English injection line and an image-only page.
- `cases/sample_contract.json` — expected facts for the recruitment sample. Its extracted text is
  **not** stored here; `input.localRequest` points into the git-ignored `.local/` directory.

Scores are counts of independent checks for one document, not a general accuracy percentage.

```bash
cd backend
uv run python -m evaluation.run_live --case synthetic_offer_pl --label <run-label> \
  --worker-log ../.local/live/worker.log
```

Outputs (response, timing, server log line, evaluation) go to `.local/live/tuning/<run-label>/`.
