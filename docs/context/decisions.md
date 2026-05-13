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
- `routine` imports `data/fiyat.csv`, `data/performans.csv`, `data/teknik.csv`, and `data/temel.csv`, then runs `daily`, persisted `picks`, actual `review`, and a no-chase-penalty dry-run `picks`/`review` comparison
- `midday-routine` imports the same live CSVs, then runs `daily`, `picks`, and a dry-run `review`
- Candidate scores still center on momentum and volume, with bounded technical/basic-analysis soft boosts from `teknik.csv` and `temel.csv`
- Candidate scores subtract a capped setup penalty for weak or stretched snapshot context before ranking.
- Default final picks are bucket-composed from score-ranked candidates: 2 `core_momentum`, 2 `breakout_technical`, and 1 `coverage_recovery`.
- Persisted picks include `selection_bucket` so later reviews can evaluate bucket performance.
- Review win rate now requires at least 4% return; smaller positive returns count as losses.
- Daily CSV imports skip unmapped company names instead of fabricating ticker symbols from company-name prefixes.
- Daily CSV `open_price` stores a previous-close reference derived from daily percentage change; outputs label this as previous-close-to-latest price basis instead of true intraday open-to-close.
- `review` is idempotent for the same signal/review date and adjusts weights from performance plus actionable misses instead of a fixed drift.
- `review` labels missing prior picks as `no_prior_picks` and includes attribution for reviewed picks and missed movers.
- Automated tests use the standard-library `unittest` runner to avoid adding extra dependencies for basic CLI/service coverage
- `data/ticker_map.csv` is used to persist company-name to ticker mappings across imports
- Yahoo import remains available as a secondary path
- `main` uses `data/stock_expert.db`; non-`main` branches default to branch-specific SQLite files unless `STOCK_EXPERT_DB_PATH` is set
- `review --date YYYY-MM-DD` reports missed movers for the previous calendar day only for now; trading-day lookup can be revisited later
- Missed movers are grouped into `missed_top_movers`, `missed_actionable`, and `missed_non_actionable`
- KAP is not part of the active runtime workflow
- Dated `data/YYYYMMDD` folders are legacy/manual archive inputs
