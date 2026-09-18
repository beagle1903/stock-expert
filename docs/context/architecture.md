# Architecture

- `stock_expert/cli.py`: command routing
- `stock_expert/services.py`: `daily`, `picks`, `review` orchestration
- `stock_expert/daily_csv.py`: imports the daily CSV snapshot files
- `stock_expert/investing_csv.py`: validates and rollback-safe publishes the four rendered Investing.com table extracts
- `scripts/investing_csv_extract.mjs`: drives a dedicated Edge/Chrome session through the browser debugging protocol without a third-party browser dependency
- `stock_expert/trading_calendar.py`: shared BIST session and exact-closure routing
- `data/ticker_map.csv`: collision-free company-name to ticker fallback used during import when a source symbol/code is missing or invalid
- `stock_expert/signals.py`: momentum, volume spike, risk classification
- `stock_expert/database.py`: SQLite schema and persistence
- `stock_expert/models.py`: domain models
- `stock_expert/config.py`: paths and thresholds
- `stock_expert/web_api.py`: loopback-only routine preview/execution adapter around the existing CLI
- `stock_expert/yahoo.py`: optional Yahoo OHLCV downloader; CSV export under `data/` except live CSVs; SQLite import publishes `yahoo_ohlcv` snapshots
- `.codex/hooks/validate_docs_update.py`: shared docs-update validator used by the leftover Codex Stop hook and the Cursor overlay adapter
- `.cursor/hooks/validate_docs_update.py`: Cursor `stop` adapter that maps validator block output to `followup_message`
- `.cursor/skills/`: Cursor operator skills for `routine`, `run`, and `refresh-data`
- `.github/workflows/ci.yml`: pull-request and `main` checks for the Python suite plus frontend tests and production build
- `frontend/`: React/Vite Evidence Console with live persisted APIs for all Evidence Console panels
- `frontend/src/data/dashboardRepository.ts`: dashboard adapter for the latest persisted review, historical review summaries, selected review detail, and captured missed-mover evidence
- `frontend/src/data/strategyPlaybackViewModel.mjs`: explicit partial and unavailable playback evidence messaging
- `frontend/src/data/routineRepository.ts`: typed HTTP adapter for routine preview/execution
- `frontend/scripts/dev.mjs`: start/reuse owner for hidden UI/API processes, ignored logs, pid files, and the post-boot observation lifecycle
- `frontend/scripts/watchdog.mjs`: injectable five-minute liveness, proxy, dashboard-semantic, and runtime-log monitor with operator summaries
- `plugins/stock-expert/skills/refresh-data/SKILL.md`: leftover Codex fallback for validated BIST CSV refresh; Cursor uses `.cursor/skills/refresh-data/SKILL.md`

## Frontend Boundary

- Presentation components consume `DashboardData` instead of importing Python or SQLite concerns.
- The latest review, pick outcomes, and captured missed movers are read from SQLite through `GET /api/reviews/latest`; historical summaries use `GET /api/reviews/history`, and selected immutable detail uses `GET /api/reviews/{id}`. Picks, diagnostics, exposure, snapshot, and timeline panels remain persisted evidence from the picks endpoint.
- `GET /api/strategy-evidence` provides bounded read-only Strategy Lab aggregates from review-owned candidate outcomes, immutable pilot sessions, and exact signal snapshots. It accepts 5/10/20/all windows plus an optional end review date and does not invoke ranking or selection logic.
- `GET /api/strategy-playback/{review_id}` returns one review-owned operational basket, exact signal snapshot context, stored strategy metadata, paired pilot arms, and eventual outcome without recomputation or latest-snapshot fallback.
- `GET /api/snapshots/history` lists every published `snapshot_runs` row newest-first (including pick-less imports). `GET /api/snapshots/{id}` returns captured provenance, mapping-failure names, and prior-snapshot comparison by `id < selected`. These routes do not invoke ranking; `/api/picks/latest` still selects the newest snapshot that owns picks.
- A successful web routine reloads the dashboard adapter so the Reviews screen reflects the newly persisted review without a page refresh.
- Data & Runs is the only mutating web surface. Its local API invokes `python -m stock_expert routine` without changing strategy or SQLite semantics.
- The dashboard does not expose order execution, live quotes, portfolios, forecasts, or target prices.

## Persistence

- SQLite tables: `snapshot_runs`, `snapshot_mapping_failures`, `stocks`, `signals`, `picks`, `weights`, `market_snapshots`, `review_runs`, `review_pick_results`, `review_missed_mover_results`, `candidate_outcomes`, `strategy_pilot_state`, `strategy_pilot_picks`, `strategy_pilot_sessions`
- `snapshot_runs` stores each live CSV import; market rows, signals, and picks reference a snapshot id
- Date-based operational reads ignore `yahoo_ohlcv` snapshots so Yahoo backfill cannot enter ranking or review price windows
- Daily snapshot publication is one transaction covering the run, market rows, price rows, and optional captured provenance (`provenance_captured=1` plus up to 50 mapping-failure names). `create_snapshot_run` and other non-CSV paths leave provenance uncaptured.
- Review runs, resulting weights, pick results, and candidate outcomes are persisted as one idempotent transaction
- Captured missed movers join that review transaction; their ordered classification and attribution are immutable on rerun, while a review-level flag keeps legacy and captured-empty states distinct
- Operational picks and both pilot baskets share one signal-publication transaction
- Pilot pick outcomes, paired session summaries, and active-state evaluation join the same review transaction when operational picks are reviewable; missing-price reviews persist an idempotent incomplete pilot session
- `strategy_pilot_state` owns the fixed pilot weights and terminal decision; `strategy_pilot_picks` owns complete signal-time arm membership and realized outcomes; `strategy_pilot_sessions` owns equal-weight arm summaries
- Review identity is database-enforced by unique signal/review dates; candidate evidence and reviewed pilot basket membership are immutable
- SQLite foreign-key enforcement is enabled for declared ownership relationships
