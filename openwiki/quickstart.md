# OpenWiki quickstart

## Repository overview

Stock Expert is a Python CLI for BIST intraday stock idea generation and review. The active runtime is daily-CSV first, with optional Yahoo OHLCV import paths for broader historical data. Commands print structured summaries, pick lists, and review diagnostics rather than free-form advice.

The main technical split is:
- `stock_expert/cli.py` for command routing
- `stock_expert/services.py` for ranking, review, diagnostics, and market-context policy
- `stock_expert/database.py` for SQLite schema and persistence
- `stock_expert/daily_csv.py` and `stock_expert/yahoo.py` for data import
- `stock_expert/config.py` and `stock_expert/trading_calendar.py` for runtime settings and session routing

This wiki is the fastest path for a new contributor or future coding agent to understand how the repo is organized, where the business logic lives, and what tests matter when changing behavior.

## What this repo does

- Imports the four daily CSV inputs: `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv`
- Stores snapshot runs, prices, signals, picks, weights, reviews, and candidate outcomes in SQLite
- Generates `daily`, `picks`, and `review` outputs from the latest imported snapshot
- Supports `routine` and `midday-routine` operator flows that import the live CSVs and then run the persisted workflow
- Exposes `download-ohlcv` and `import-ohlcv-excel` as secondary Yahoo data paths
- Keeps trading-day routing consistent through a shared calendar and exact-closure handling

## Start here

1. [Runtime architecture](architecture/runtime.md) â€” execution flow, module map, and persistence design
2. [Picks and review domain](domains/picks-review.md) â€” scoring, selection buckets, market context, and review rules
3. [Data and operations](operations/data-and-operations.md) â€” configuration, database path behavior, and operator commands
4. [Testing guidance](testing/testing.md) â€” test coverage map and what to run when changing behavior

## Key source references

- CLI routing: `stock_expert/cli.py`
- Workflow orchestration: `stock_expert/services.py`
- SQLite schema and persistence helpers: `stock_expert/database.py`
- Configuration and database-path selection: `stock_expert/config.py`
- Trading-day rules: `stock_expert/trading_calendar.py`
- CSV import pipeline: `stock_expert/daily_csv.py`
- Yahoo import pipeline: `stock_expert/yahoo.py`
- Domain models and score rows: `stock_expert/models.py`, `stock_expert/signals.py`

## Existing docs that remain useful

The repository already includes a detailed `docs/` tree. OpenWiki does not replace it; it maps it.

- `README.md` â€” repository-level command examples
- `docs/context/project.md` â€” compact project summary
- `docs/context/architecture.md` â€” architecture and persistence notes
- `docs/context/decisions.md` â€” evolving decisions and operational gotchas
- `docs/features/daily.md`, `docs/features/picks.md`, `docs/features/review.md` â€” feature notes

## Change guidance for future agents

- When changing CLI behavior, inspect `stock_expert/cli.py` and `tests/test_cli.py` first.
- When changing ranking, review, or market-context behavior, inspect `stock_expert/services.py`, `stock_expert/signals.py`, and `tests/test_services.py`.
- When changing persistence or snapshot semantics, inspect `stock_expert/database.py` plus the database-focused tests.
- When changing imports, calendar behavior, or path selection, check `stock_expert/daily_csv.py`, `stock_expert/yahoo.py`, `stock_expert/trading_calendar.py`, and `stock_expert/config.py`.
- Preserve structured outputs and avoid future-data leakage unless a deliberate design change says otherwise.

## Navigation map

- [Runtime architecture](architecture/runtime.md)
- [Picks and review domain](domains/picks-review.md)
- [Data and operations](operations/data-and-operations.md)
- [Testing guidance](testing/testing.md)