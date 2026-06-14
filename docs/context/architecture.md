# Architecture

- `stock_expert/cli.py`: command routing
- `stock_expert/services.py`: `daily`, `picks`, `review` orchestration
- `stock_expert/daily_csv.py`: imports the daily CSV snapshot files
- `stock_expert/trading_calendar.py`: shared BIST session and exact-closure routing
- `data/ticker_map.csv`: persistent company-name to ticker overrides used during import
- `stock_expert/signals.py`: momentum, volume spike, risk classification
- `stock_expert/database.py`: SQLite schema and persistence
- `stock_expert/models.py`: domain models
- `stock_expert/config.py`: paths and thresholds
- `stock_expert/yahoo.py`: Yahoo OHLCV downloader with CSV export and optional SQLite import
- `.codex/hooks/validate_docs_update.py`: deterministic Codex Stop hook validator for development documentation updates

## Persistence

- SQLite tables: `snapshot_runs`, `stocks`, `signals`, `picks`, `weights`, `market_snapshots`, `review_runs`, `review_pick_results`, `candidate_outcomes`
- `snapshot_runs` stores each live CSV import; market rows, signals, and picks reference a snapshot id
- Date-based reads use the latest snapshot for each date
- Daily snapshot publication is one transaction covering the run, market rows, and price rows
- Review runs, resulting weights, pick results, and candidate outcomes are persisted as one idempotent transaction
- Review identity is database-enforced by unique signal/review dates; candidate evidence belongs to the immutable review run
- SQLite foreign-key enforcement is enabled for declared ownership relationships
