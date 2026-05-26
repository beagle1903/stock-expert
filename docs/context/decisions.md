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
- `routine` imports `data/fiyat.csv`, `data/performans.csv`, `data/teknik.csv`, and `data/temel.csv`, then runs `daily`, persisted `picks`, actual `review`, score-ranked vs bucketed review comparison, and downside-risk diagnostics
- `midday-routine` imports the same live CSVs, then runs `daily`, `picks`, and a dry-run `review`
- Candidate scores still center on momentum and volume, with bounded technical/basic-analysis soft boosts from `teknik.csv` and `temel.csv`
- Candidate scores subtract a capped setup penalty for weak or stretched snapshot context before ranking.
- Default persisted picks are score-ranked top 5 after recent DB-backed checks favored score-ranked selection over bucketed selection.
- Bucket-composed picks remain available for dry-run/reporting comparison: 2 `core_momentum`, 2 `breakout_technical`, and 1 `coverage_recovery`.
- Persisted and comparison picks include `selection_bucket` so later reviews can evaluate selection behavior.
- Review win rate now requires at least 4% return; smaller positive returns count as losses.
- Market holidays are exact confirmed closed dates, not recurring month/day rules; religious holidays shift each year.
- The 2026 holiday-week routing treats 2026-05-26 as a half-holiday/low-liquidity context, skips 2026-05-27 through 2026-05-29, and leaves 2026-06-01 open.
- Daily CSV imports skip unmapped company names instead of fabricating ticker symbols from company-name prefixes.
- Daily CSV `open_price` stores a previous-close reference derived from daily percentage change; outputs label this as previous-close-to-latest price basis instead of true intraday open-to-close.
- `review` is idempotent for the same signal/review date and adjusts weights from performance plus actionable misses instead of a fixed drift.
- `review` labels missing prior picks as `no_prior_picks` and includes attribution for reviewed picks and missed movers.
- Automated tests use the standard-library `unittest` runner to avoid adding extra dependencies for basic CLI/service coverage
- `data/ticker_map.csv` is used to persist company-name to ticker mappings across imports
- Yahoo import remains available as a secondary path
- `main` uses `data/stock_expert.db`; non-`main` branches default to branch-specific SQLite files unless `STOCK_EXPERT_DB_PATH` is set
- `review --date YYYY-MM-DD` evaluates the previous trading-day signal picks against the requested review date and reports missed movers for that review date
- Missed movers are grouped into `missed_top_movers`, `missed_actionable`, and `missed_non_actionable`
- KAP is not part of the active runtime workflow
- Dated `data/YYYYMMDD` folders are legacy/manual archive inputs
