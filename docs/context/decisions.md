# Decisions

- Keep the MVP in Python with standard-library-first tooling
- Use SQLite for local persistence
- Keep outputs structured
- No future data leakage
- Only use data available at decision time
- Daily CSV snapshots are the main operating input

## Current Notes

- Daily CSV imports are the main runtime market-data source
- `data/ticker_map.csv` is used to persist company-name to ticker mappings across imports
- Yahoo import remains available as a secondary path
- `review` recalculates the rolling 7-day window
- `review` currently updates weights on every run for the same date
- Missed movers are grouped into `missed_top_movers`, `missed_actionable`, and `missed_non_actionable`
- KAP is not part of the active runtime workflow
