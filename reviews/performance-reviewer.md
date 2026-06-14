# Performance Review

Scope: full codebase plus `git diff HEAD~5..HEAD`. No production code or live data was changed.

## P1: Routine recomputes identical rankings up to eight times

**References:** `stock_expert/cli.py:192-207`, `stock_expert/services.py:138-160`, `stock_expert/services.py:252-333`, `stock_expert/services.py:550`, `stock_expert/services.py:572`, `stock_expert/services.py:632`, `stock_expert/services.py:719-727`, `stock_expert/services.py:786`, `stock_expert/services.py:894-906`, `stock_expert/services.py:985`

**Impact:** CLI latency and SQLite reads grow by roughly 8x the cost of one ranking pass. Each pass reloads and sorts ten sessions of prices, reconstructs all signals, reloads latest prices/snapshots/weights, and sorts the universe.

**Evidence:** Instrumenting `picks_output`, dry-run `review_output`, strategy comparison, and downside diagnostics produced 6 `build_signals` calls, 6 recent-history loads, 7 date-price loads, and 9 weight loads. The real routine additionally ranks in `daily_summary`; persisted review adds another bucketed ranking. A standalone dry-run picks command took about 464 ms on the current 36,066-row database.

**Suggested fix:** Introduce a request-scoped `RankingContext` containing ranked candidates, signals, snapshot id, prices, snapshots, weights, and exposure. Compute it once per signal date in `routine`, then pass it to daily, picks, review attribution, bucketed selection, comparison, and downside formatting. Keep public commands able to build their own context.

## P1: Yahoo bulk import performs schema/query work once per OHLCV row

**References:** `stock_expert/database.py:147-152`, `stock_expert/database.py:264-290`, `stock_expert/database.py:313-321`, `stock_expert/yahoo.py:141-190`, `stock_expert/yahoo.py:221-266`

**Impact:** Importing `T` tickers over `D` dates performs `T*D` snapshot lookups. Every lookup calls `init_db`, opens a connection, executes the full schema, and runs migration checks. Large imports can spend most time in SQLite setup rather than insertion.

**Evidence:** A synthetic 500-ticker x 30-day input caused 15,000 `get_latest_snapshot_id` calls before the single `executemany`. This is an N-row database round-trip pattern.

**Suggested fix:** Materialize rows once, collect distinct dates, resolve/create one snapshot id per date in a single connection/transaction, map rows in memory, then execute one bulk upsert. Make `init_db` an application-start/migration operation rather than a per-query dependency.

## P2: Date-oriented queries have no supporting indexes

**References:** `stock_expert/database.py:13-132`, `stock_expert/database.py:277-310`, `stock_expert/database.py:548-597`

**Impact:** Snapshot, review, and diagnostic lookups degrade to table scans and temporary B-trees as history grows.

**Evidence:** `EXPLAIN QUERY PLAN` reports scans for latest snapshot and review lookup. Candidate diagnostics scan `candidate_outcomes` and create temporary B-trees for distinct/order operations. Current tables contain 69 snapshot runs, 42 reviews, and 300 outcomes, so impact is currently masked.

**Suggested fix:** Add indexes on `snapshot_runs(snapshot_date, id DESC)`, `review_runs(as_of_date, review_date, id DESC)`, and `candidate_outcomes(review_date DESC, candidate_rank)`. Add query-plan tests against representative data.

## P2: Yahoo downloads retain two full copies of all rows

**References:** `stock_expert/yahoo.py:141-178`, `stock_expert/yahoo.py:221-253`

**Impact:** `csv_rows` dictionaries and `db_rows` tuples grow together for the complete download, increasing peak memory and delaying persistence until all network work finishes.

**Suggested fix:** Stream CSV output and flush database rows in bounded batches, while retaining only counters, failures, and downloaded ticker names.

## Residual Risks / Test Gaps

- No routine-level performance budget or ranking-call-count regression test.
- No benchmark covering multi-year Yahoo imports.
- No representative large-history SQLite query-plan test.

## Summary

No P0 findings. Two P1 issues can dominate CLI/import latency; two P2 issues will matter as persisted history or download ranges grow.
