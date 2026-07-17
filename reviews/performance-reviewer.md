# Performance Review

Scope: full production code, tests/docs, current worktree, and recent commits through `9ff2846`. No production code or durable data was changed. Read-only checks used the current 17.2 MB SQLite database (96 snapshot runs; 49,707 price rows; 1,299 candidate outcomes).

## P0

No P0 performance findings.

## P1: Database initialization and connection churn remain on every hot-path read

**Evidence:** `stock_expert/database.py:160-166` runs the full schema plus all migration/integrity checks; many getters call it directly (`:359-372`, `:596-608`, `:647-676`, `:679-718`, `:997-1016`, `:1019-1034`). `get_prices_for_date` and `get_market_snapshots_for_date` first call `get_latest_snapshot_id`, so each logical read opens multiple connections. A read-only instrumented full diagnostic flow (`daily`, picks, review, comparison, downside risk) recorded **40 `init_db` calls and 61 query connections even after initialization itself was replaced with a no-op**. `RankingContext` at `stock_expert/services.py:46-49` caches only ranked rows.

**Impact:** Repeated DDL parsing, PRAGMAs, schema inspection, duplicate-review scans, commits, and SQLite opens dominate local work as commands and history grow; they also extend lock windows during the persisted routine.

**Suggested fix:** Initialize/migrate once in `cli.main`, make repository getters migration-free, and introduce one request-scoped data context/connection that caches snapshot ids, prices, snapshots, weights, candidate outcomes, and exposure per date. Add a routine regression test asserting bounded initialization/query counts.

## P1: Historical Yahoo import ignores the requested end date while downloading

**Evidence:** `stock_expert/yahoo.py:36-44` always requests through the current time. `import_ohlcv_excel_command` computes `lookback_days` from today to `start` (`:225`) and only discards rows after download (`:237-240`). Thus a request for a closed historical interval downloads every session from the requested start through today for every ticker.

**Impact:** Old ranges cause years of unnecessary network transfer, JSON parsing, retries, and provider load. Runtime grows with `today - start`, not the requested interval.

**Suggested fix:** Change the fetch API to accept explicit `period1`/`period2` (with a small boundary buffer), pass the requested start/end, and test that a past one-month import emits a one-month Yahoo query.

## P2: Adaptive exposure diagnostics are recomputed throughout one routine

**Evidence:** `adaptive_pick_exposure` loads and re-aggregates candidate outcomes (`stock_expert/services.py:406-437`). The same flow calls it from pick generation, pick formatting, review, comparison, and downside diagnostics (`:369-395`, `:651-709`, `:1006-1126`). Instrumentation observed **7 candidate-outcome loads**. The current indexed query took about **610 ms for 100 executions**; one execution is small, but repetition is avoidable.

**Impact:** The June adaptive-selection change reintroduced repeated DB/aggregation work around the ranking cache, and cost grows with the rolling window and candidate cap.

**Suggested fix:** Cache `(before_review_date, limit_sessions)` outcomes/diagnostics and per-date exposure in `RankingContext`; pass the computed exposure into formatting/review helpers.

## P2: Bulk Yahoo paths retain duplicate full result sets

**Evidence:** Both download paths accumulate dictionary `csv_rows` and tuple `db_rows` for every retained row before sorting/writing/importing (`stock_expert/yahoo.py:141-190`, `:221-266`). Requests are also strictly serial with a new `urlopen` connection per ticker (`:45`, `:146-181`, `:227-260`).

**Impact:** Multi-year, market-wide imports consume memory proportional to all rows twice and delay durable progress until the final ticker; serial TLS/request overhead compounds the configured throttling.

**Suggested fix:** Stream CSV rows and flush SQLite rows in bounded transactional batches. Keep conservative rate limits; if concurrency is added, make it small/configurable and backoff-aware.

## P2: Review-date lookup lacks a supporting index

**Evidence:** `get_recent_review_runs` filters/orders by `review_date` (`stock_expert/database.py:694-718`), but schema indexes only review identity `(as_of_date, review_date)` (`:306-310`). `EXPLAIN QUERY PLAN` on the live DB reports a full `review_runs` scan plus a temporary B-tree for ordering.

**Impact:** Currently masked by 54 rows, but review history makes each rolling-weight lookup increasingly scan/sort bound.

**Suggested fix:** Add `review_runs(review_date DESC)` (optionally a partial index for `pick_count > 0`) and a representative query-plan test.

## Sound performance-sensitive areas

- Latest-snapshot and candidate-outcome indexes are used by SQLite; the previous review's missing-index findings were substantially fixed.
- `upsert_prices` resolves distinct dates once and uses `executemany`; the former per-row snapshot lookup was fixed.
- Ranking is linear over the universe plus one `O(N log N)` sort, and signal windows are bounded to ten sessions.
- Atomic bulk snapshot/review transactions and bounded 20-session/50-candidate diagnostics keep write and analysis sets controlled.
- Daily CSV/XLSX in-memory parsing is acceptable for the current BIST-sized inputs; the scaling concern is specifically large OHLCV history.
