# Data and operations

## Configuration and paths

`stock_expert/config.py` derives runtime settings from the repository location.

Important behavior:

- `.env` is loaded if present, but only missing environment variables are filled
- `STOCK_EXPERT_DB_PATH` overrides the SQLite database location
- on `main`, the default database is `data/stock_expert.db`
- on feature branches, the default database is branch-specific so runs do not collide
- detached HEAD or git failures use isolated fallback database names
- the `data/` directory is created automatically

## Core data inputs

### Daily CSV snapshot inputs

The primary runtime inputs are the four CSV files in the data folder:

- `fiyat.csv`
- `performans.csv`
- `teknik.csv`
- `temel.csv`

`stock_expert/daily_csv.py` merges these files, normalizes Turkish headers, filters obvious non-equity rows, applies ticker overrides from `data/ticker_map.csv`, and writes a snapshot bundle to SQLite.

### Yahoo OHLCV import path

`stock_expert/yahoo.py` can download OHLCV history from Yahoo Finance, write a CSV export, and optionally import those rows into SQLite.

## SQLite storage

The database keeps workflow state in one SQLite file. Key tables include import history, prices, signals, picks, weights, market snapshots, reviews, and candidate outcomes.

A few storage behaviors matter for future changes:

- snapshot imports are published atomically only after validation succeeds
- review bundles are persisted as a single idempotent transaction
- review evidence is immutable on rerun for the same signal/review date
- older schema variants can be migrated into the current snapshot-run layout

## Operator commands

- `daily` — market summary
- `picks` — compute picks, optionally dry-run only
- `review` — evaluate previous signal-day picks against a review date
- `download-ohlcv` — fetch Yahoo data for a ticker list
- `import-ohlcv-excel` — fetch Yahoo data from workbook-derived tickers
- `import-daily-csv` — import the four daily CSV files for a date
- `import-daily-folder` — import a dated archive folder
- `routine` — full persisted operator routine
- `midday-routine` — same as routine, but review stays dry-run

## Operational cautions

- Keep `.env` non-sensitive and local only.
- Preserve the exact trading-session calendar when adding or moving date logic.
- The repo expects structured output.
- `routine` and `midday-routine` should continue to share ranking context when possible.
- The default DB path differs by branch, which is useful but easy to forget when comparing state across checkouts.
