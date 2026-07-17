# Runtime architecture

## Overview

The application is a CLI-first workflow engine for intraday BIST stock selection and review. The CLI routes commands into service-layer functions that build signals, rank candidates, persist selections, and format structured JSON or report-style text.

The main runtime split is:

- `stock_expert/cli.py` — command parsing and top-level routing
- `stock_expert/services.py` — orchestration for daily summary, picks, review, diagnostics, and market context
- `stock_expert/database.py` — SQLite schema, reads, writes, and migration helpers
- `stock_expert/config.py` — project paths, branch-aware database selection, and runtime thresholds
- `stock_expert/trading_calendar.py` — shared holiday/weekend routing
- `stock_expert/daily_csv.py` and `stock_expert/yahoo.py` — market-data import paths

## Execution flow

### Normal operator workflow

1. A command such as `daily`, `picks`, `review`, `routine`, or `midday-routine` is parsed in `stock_expert/cli.py`.
2. The CLI loads settings through `get_settings()`.
3. Service functions query SQLite and/or imported snapshot data, then compute ranking and review output.
4. The command prints structured JSON or report text to stdout.

### Routine workflow

The `routine` command is the most complete operator path. It:

- imports the current root daily CSV files
- prints market context
- runs the daily summary
- generates persisted picks
- runs the persisted review
- prints score-ranked vs bucketed comparison diagnostics
- prints downside-risk diagnostics

`midday-routine` uses the same import and ranking path, but keeps the review step in dry-run mode.

## Key modules and responsibilities

### `stock_expert/cli.py`

The CLI defines subcommands for:

- `daily`
- `picks`
- `review`
- `download-ohlcv`
- `import-ohlcv-excel`
- `import-daily-csv`
- `import-daily-folder`
- `routine`
- `midday-routine`

The `routine` and `midday-routine` commands reuse a `RankingContext` so each signal-date ranking is computed once per run.

### `stock_expert/services.py`

This is the main orchestration layer. It contains:

- signal construction from recent price history
- score ranking and pick selection
- market context tagging and political-shock / low-liquidity policy
- review generation and review-weight updates
- bucketed selection diagnostics and downside-risk reporting

### `stock_expert/database.py`

The database layer owns:

- schema creation
- snapshot-run migration for older schemas
- price, signal, pick, and review persistence
- read helpers for latest snapshots, recent price history, movers, review results, and candidate outcomes

### `stock_expert/config.py`

Settings are derived from the repo root. Notable behavior:

- `.env` can provide local overrides, but only for missing environment variables
- `STOCK_EXPERT_DB_PATH` overrides the database path
- on `main`, the default DB is `data/stock_expert.db`
- on other branches, the default DB is branch-specific to avoid clobbering shared state
- detached HEAD or git detection failures fall back to isolated DB files

### `stock_expert/trading_calendar.py`

This module centralizes session routing and exact-market-closure dates. The comments and tests make clear that confirmed exchange-closed dates are intentionally stored as exact dates rather than recurring holiday rules.

### `stock_expert/daily_csv.py`

The import pipeline normalizes Turkish headers, joins the four daily CSV sources, filters non-equity rows, maps companies to tickers, and persists snapshot rows plus price rows atomically.

### `stock_expert/yahoo.py`

Yahoo import is a secondary path. It can download OHLCV data for a list of tickers, write a CSV export, and optionally import price rows into SQLite.

## Persistence model

The SQLite schema in `stock_expert/database.py` centers on these tables:

- `snapshot_runs` — import history and snapshot identity
- `stocks` — imported price rows
- `signals` — computed signal rows
- `picks` — selected candidates
- `weights` — persisted weighting state
- `market_snapshots` — enriched market context rows
- `review_runs` — review metadata and summary metrics
- `review_pick_results` — per-pick realized performance
- `candidate_outcomes` — rank-window evidence for review and cutoff analysis

Snapshot identity is important: market rows, signals, and picks are tied to a specific snapshot id rather than only a date, so multiple imports on the same date can coexist.

## Why this structure exists

Recent history shows the runtime has been tightened around a few stable principles:

- keep the workflow deterministic and structured
- avoid future-data leakage
- use SQLite as the authoritative local store
- preserve daily CSV snapshots as the primary runtime source
- let the CLI orchestrate, while the service layer carries the strategy logic
- keep review and candidate evidence immutable once persisted

## Change guidance

- If you change command flow, update `stock_expert/cli.py` and the CLI tests together.
- If you change how ranking or review is computed, inspect service tests for cached ranking, review idempotence, and bucket diagnostics.
- If you change schema shape, update database helpers and migration paths carefully; the schema is expected to absorb older snapshots.
- If you change calendar routing, verify all commands that derive previous/next sessions.

## Source map

- CLI: `stock_expert/cli.py`
- Orchestration: `stock_expert/services.py`
- Persistence: `stock_expert/database.py`
- Settings: `stock_expert/config.py`
- Calendar: `stock_expert/trading_calendar.py`
- Daily import: `stock_expert/daily_csv.py`
- Yahoo import: `stock_expert/yahoo.py`