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

This means most local work can happen without editing configuration files, but the path rules matter when comparing branch results or running review workflows.

## Core data inputs

### Daily CSV snapshot inputs

The primary runtime inputs are the four CSV files in the data folder:

- `fiyat.csv`
- `performans.csv`
- `teknik.csv`
- `temel.csv`

`stock_expert/daily_csv.py` merges these files, normalizes Turkish headers, filters obvious non-equity rows, applies ticker overrides from `data/ticker_map.csv`, and writes a snapshot bundle to SQLite.

The import output records counts for mapped rows, unmapped rows, malformed rows, and non-equity skips. It also labels the price basis as a previous-close-to-latest calculation derived from the daily percentage change.

### Yahoo OHLCV import path

`stock_expert/yahoo.py` can download OHLCV history from Yahoo Finance, write a CSV export, and optionally import those rows into SQLite.

There are two entrypoints here:

- `download-ohlcv` — fetches tickers directly and writes a CSV export
- `import-ohlcv-excel` — reads ticker codes from an Excel workbook and imports a date range

This path is present as a secondary data source, while daily CSV snapshots remain the main runtime source.

## SQLite schema and storage

The database layer keeps the workflow state in one SQLite file. Key tables include import history, prices, signals, picks, weights, market snapshots, reviews, and candidate outcomes.

A few storage behaviors matter for future changes:

- snapshot imports are published atomically only after validation succeeds
- review bundles are persisted as a single idempotent transaction
- review evidence is immutable on rerun for the same signal/review date
- latest reads often pick the most recent snapshot for a given date
- older schema variants can be migrated into the current snapshot-run layout

## Operator commands

The CLI commands are intentionally narrow and map to specific operational workflows:

- `daily` — produce a market summary
- `picks` — compute picks, optionally dry-run only
- `review` — evaluate previous signal-day picks against a review date, optionally dry-run only
- `download-ohlcv` — fetch Yahoo data for a ticker list
- `import-ohlcv-excel` — fetch Yahoo data from workbook-derived tickers
- `import-daily-csv` — import the four daily CSV files for a date
- `import-daily-folder` — import a dated archive folder
- `routine` — full persisted operator routine
- `midday-routine` — same as routine, but review stays dry-run

If you are changing user-facing behavior, `stock_expert/cli.py` and `tests/test_cli.py` are the fastest places to verify the expected command shape.

## Operational cautions

- Keep `.env` non-sensitive and local only; do not document secrets.
- Preserve the exact trading-session calendar when adding or moving date logic.
- The repo expects structured output; avoid replacing machine-readable output with prose-only summaries.
- `routine` and `midday-routine` should continue to share ranking context when possible so repeated ranking work is not duplicated.
- The default DB path differs by branch, which is useful but easy to forget when comparing state across checkouts.

## What to inspect when changing this area

- `stock_expert/config.py` for path and environment behavior
- `stock_expert/database.py` for schema, migrations, and persistence semantics
- `stock_expert/daily_csv.py` for snapshot import rules
- `stock_expert/yahoo.py` for external data import paths
- `README.md` for repo-level command examples and quick setup hints

## Source references

- Configuration: `stock_expert/config.py`
- DB schema and persistence: `stock_expert/database.py`
- Daily CSV import: `stock_expert/daily_csv.py`
- Yahoo import: `stock_expert/yahoo.py`
- Command examples: `README.md`