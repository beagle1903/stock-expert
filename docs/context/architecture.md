# Architecture

- `stock_expert/cli.py`: command routing
- `stock_expert/services.py`: `daily`, `picks`, `review` orchestration
- `stock_expert/daily_csv.py`: imports the daily CSV snapshot files
- `stock_expert/investing_csv.py`: validates and rollback-safe publishes the four rendered Investing.com table extracts
- `scripts/investing_csv_extract.mjs`: drives a dedicated Edge/Chrome session through the browser debugging protocol without a third-party browser dependency
- `stock_expert/trading_calendar.py`: shared BIST session and exact-closure routing
- `data/ticker_map.csv`: persistent company-name to ticker overrides used during import
- `stock_expert/signals.py`: momentum, volume spike, risk classification
- `stock_expert/database.py`: SQLite schema and persistence
- `stock_expert/models.py`: domain models
- `stock_expert/config.py`: paths and thresholds
- `stock_expert/web_api.py`: loopback-only routine preview/execution adapter around the existing CLI
- `stock_expert/yahoo.py`: Yahoo OHLCV downloader with CSV export and optional SQLite import
- `.codex/hooks/validate_docs_update.py`: deterministic Codex Stop hook validator for development documentation updates
- `frontend/`: React/Vite Evidence Console with a live persisted-review read and typed sample data for deferred panels
- `frontend/src/data/dashboardRepository.ts`: dashboard adapter for the latest persisted review, historical review summaries, and selected review detail
- `frontend/src/data/routineRepository.ts`: typed HTTP adapter for routine preview/execution
- `plugins/stock-expert/skills/refresh-data/SKILL.md`: validated BIST CSV refresh and direct Data & Runs handoff

## Frontend Boundary

- Presentation components consume `DashboardData` instead of importing Python or SQLite concerns.
- The latest review and its pick outcomes are read from SQLite through `GET /api/reviews/latest`; historical summaries use `GET /api/reviews/history`, and selected immutable outcomes use `GET /api/reviews/{id}`. Picks, diagnostics, exposure, snapshot, and timeline panels remain sample evidence.
- A successful web routine reloads the dashboard adapter so the Reviews screen reflects the newly persisted review without a page refresh.
- Data & Runs is the only mutating web surface. Its local API invokes `python -m stock_expert routine` without changing strategy or SQLite semantics.
- The dashboard does not expose order execution, live quotes, portfolios, forecasts, or target prices.

## Persistence

- SQLite tables: `snapshot_runs`, `stocks`, `signals`, `picks`, `weights`, `market_snapshots`, `review_runs`, `review_pick_results`, `candidate_outcomes`, `strategy_pilot_state`, `strategy_pilot_picks`, `strategy_pilot_sessions`
- `snapshot_runs` stores each live CSV import; market rows, signals, and picks reference a snapshot id
- Date-based reads use the latest snapshot for each date
- Daily snapshot publication is one transaction covering the run, market rows, and price rows
- Review runs, resulting weights, pick results, and candidate outcomes are persisted as one idempotent transaction
- Operational picks and both pilot baskets share one signal-publication transaction
- Pilot pick outcomes, paired session summaries, and active-state evaluation join the same review transaction when operational picks are reviewable; missing-price reviews persist an idempotent incomplete pilot session
- `strategy_pilot_state` owns the fixed pilot weights and terminal decision; `strategy_pilot_picks` owns complete signal-time arm membership and realized outcomes; `strategy_pilot_sessions` owns equal-weight arm summaries
- Review identity is database-enforced by unique signal/review dates; candidate evidence and reviewed pilot basket membership are immutable
- SQLite foreign-key enforcement is enabled for declared ownership relationships
