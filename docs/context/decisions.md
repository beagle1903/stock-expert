# Decisions

- Keep the MVP in Python with standard-library-first tooling
- Use SQLite for local persistence
- Keep outputs structured
- No future data leakage
- Only use data available at decision time
- Daily CSV snapshots are the main operating input
- Live root CSV files are the default input; SQLite snapshot runs preserve import history

## Current Notes

- Daily CSV imports are the main runtime market-data source
- `routine` imports `data/fiyat.csv`, `data/performans.csv`, `data/teknik.csv`, and `data/temel.csv`, then runs `daily`, `picks`, and actual `review`
- `midday-routine` imports the same live CSVs, then runs `daily`, `picks`, and a dry-run `review`
- Picks still center on momentum and volume, but now add bounded technical/basic-analysis soft boosts from `teknik.csv` and `temel.csv`
- Automated tests use the standard-library `unittest` runner to avoid adding extra dependencies for basic CLI/service coverage
- `data/ticker_map.csv` is used to persist company-name to ticker mappings across imports
- Yahoo import remains available as a secondary path
- `main` uses `data/stock_expert.db`; non-`main` branches default to branch-specific SQLite files unless `STOCK_EXPERT_DB_PATH` is set
- `review --date YYYY-MM-DD` reports missed movers for the previous calendar day only for now; trading-day lookup can be revisited later
- `review` currently updates weights on every run for the same date
- Missed movers are grouped into `missed_top_movers`, `missed_actionable`, and `missed_non_actionable`
- KAP is not part of the active runtime workflow
- Dated `data/YYYYMMDD` folders are legacy/manual archive inputs
