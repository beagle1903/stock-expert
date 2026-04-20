# Architecture

- `stock_expert/cli.py`: command routing
- `stock_expert/services.py`: `daily`, `picks`, `review` orchestration
- `stock_expert/daily_csv.py`: imports the daily CSV snapshot files
- `data/ticker_map.csv`: persistent company-name to ticker overrides used during import
- `stock_expert/signals.py`: momentum, volume spike, risk classification
- `stock_expert/database.py`: SQLite schema and persistence
- `stock_expert/models.py`: domain models
- `stock_expert/config.py`: paths and thresholds
- `stock_expert/yahoo.py`: Yahoo OHLCV downloader with CSV export and optional SQLite import

## Persistence

- SQLite tables: `snapshot_runs`, `stocks`, `signals`, `picks`, `weights`, `market_snapshots`
- `snapshot_runs` stores each live CSV import; market rows, signals, and picks reference a snapshot id
- Date-based reads use the latest snapshot for each date
