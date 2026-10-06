---
name: bist
description: Refresh Stock Expert's four Investing.com BIST CSVs in Cursor's embedded browser, publish a validated bundle, then run the persisted routine. Use when the user says /bist, bist plugin, refresh then routine, or asks to update BIST data and run the routine without the web app.
---

# BIST Refresh Then Routine

Refresh the four live Investing.com CSVs in Cursor's embedded browser, publish only a validated bundle, then run the persisted routine. Do not start the web app.

## Preflight

1. Confirm the working directory is `C:\Users\burha\Documents\dev\stock expert`.
2. Read `memory.md`, `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
3. Record `git status --short` and preserve unrelated worktree changes.

## Refresh

Use only Cursor's in-app browser (`cursor-ide-browser`). Do not launch or fall
back to standalone Chrome or Edge. Do not run
`D:\miniconda3\python.exe -m stock_expert refresh-investing-csvs` or
`scripts/investing_csv_extract.mjs`. That launcher is not an embedded-browser
adapter.

1. Open `https://tr.investing.com/equities/turkey`. Confirm the Turkish labels
   Fiyat, Performans, Teknik, and Temel.
2. If Cloudflare, CAPTCHA, or another access challenge is waiting on the user,
   stop and ask them to complete it in the embedded browser. Do not bypass it.
3. Select `Türkiye tüm hisse senetleri` when the market selector is not already
   that market.
4. Expand with the equity-table footer control whose visible text is exactly
   `Daha Fazla` (the cursor-pointer row under the table). Do not click
   navigation items that merely contain the words Daha Fazla. Scroll that
   footer into view, click it, and wait until the tbody row count increases.
   Repeat until the footer control is gone. Stop as a failure if it is still
   present after 12 clicks or the table stalls below 500 rows.
5. Switching tabs keeps the expanded rows. Do not click `Daha Fazla` again
   unless that footer control reappears. Capture `fiyat.csv`, `performans.csv`,
   `teknik.csv`, and `temel.csv` from the rendered table. Include an optional
   symbol column only when it is immediately before or after İsim.
6. Publish once, with all four tables, through
   `stock_expert.investing_csv.publish_extracted_tables` into `data/` at
   `min_rows=500`. Do not publish a partial bundle and do not write the CSV
   files by hand. From the repository root, call it with
   `D:\miniconda3\python.exe`. The payload `tables` object must contain
   `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv`. Each value is
   `{"headers": [...], "rows": [[...], ...]}` taken from the rendered table:

```python
from pathlib import Path
from stock_expert.investing_csv import publish_extracted_tables

publish_extracted_tables(payload, destination=Path("data"), min_rows=500)
```

7. Success requires matching company coverage, expected schemas, each file
   non-empty and starting with the UTF-8 BOM, and each file at least the
   minimum row count. The publish function enforces coverage, schemas, and
   `min_rows`, and it writes UTF-8 with a BOM. Still confirm each file in
   `data/` is non-empty and begins with the UTF-8 BOM (`EF BB BF`). Record
   `git status --short` after publication.
8. If any refresh or publication check fails, stop. Do not run `routine`.

## Routine

Run this section only after a clean publication.

1. Run:

```powershell
D:\miniconda3\python.exe -m stock_expert routine
```

2. Verify the printed `snapshot_id`, `review_run_id`, and related
   `review_pick_results` rows in the active SQLite database. `main` uses
   `data/stock_expert.db`. Other branches use `data/stock_expert_<branch>.db`
   unless `STOCK_EXPERT_DB_PATH` overrides it.
3. Run `git status --short`.
4. Report the pick basket, review result, snapshot/review ids, signal and
   target/review dates, SQLite verification, publication row counts, and git
   status.
5. Do not start `frontend/scripts/dev.mjs` or open `http://127.0.0.1:5173`.
