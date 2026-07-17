# Parallel Code Review Summary

## Review status

Five specialist reviews completed: security, architecture, test coverage, performance, and business logic. Reviewers inspected the full codebase and recent Git changes. The test reviewer independently verified **93/93 tests pass** and **94.18% weighted production trace coverage**. No P0 issue was found.

## P0 — Critical

None.

## P1 — High priority

### 1. Preserve immutable snapshot and review evidence

Yahoo imports can overwrite rows in an already-published daily snapshot (`stock_expert/yahoo.py:187-190,265-266`; `stock_expert/database.py:395-445`). Persisted review reruns also recompute results from current latest snapshots while reusing the old review identity (`stock_expert/services.py:1015-1173`). Together these can make historical output disagree with stored audit evidence.

**Actionable agent prompt:**

> Refactor ingestion so every source publishes a source-owned immutable `snapshot_run`; require explicit snapshot ownership in low-level writers and remove cross-source latest-snapshot mutation. For non-dry-run reviews, detect an existing review before recomputation and hydrate the complete response from review-owned rows and persisted snapshot/version metadata. Keep live recomputation in an explicitly labeled dry-run/comparison path. Add regression tests proving Yahoo imports cannot mutate daily CSV snapshots and persisted review reruns remain stable after newer same-date imports or strategy changes. Update architecture, persistence, and feature docs.

### 2. Repair and test legacy SQLite ownership migrations

Upgrades add nullable `candidate_outcomes.review_run_id` without backfill or an actual foreign key, diverging from the fresh schema (`stock_expert/database.py:118-137,278-305`). Destructive legacy migrations are largely unexecuted by tests.

**Actionable agent prompt:**

> Implement a transactional, versioned table-rebuild migration for `candidate_outcomes`: map legacy rows to retained review runs, define orphan/duplicate handling, enforce `NOT NULL` and the foreign key, and validate with `PRAGMA foreign_key_check`. Add pre-migration SQLite fixtures for every supported legacy shape; run `init_db` twice and assert preservation, ownership, indexes, idempotency, duplicate cleanup, and rollback on forced failure. Update schema/decision docs.

### 3. Complete the authoritative BIST trading calendar

The hard-coded calendar omits confirmed full-day closures, including 2026-04-23 and the imminent 2026-07-15 (`stock_expert/trading_calendar.py:6-18`). This can route picks, imports, and reviews to non-trading dates.

**Actionable agent prompt:**

> Replace the partial closure list with a versioned authoritative annual BIST calendar supporting full closures and half-days. Add 2026-04-23 and 2026-07-15 immediately, define routine behavior on closed dates, and add forward/backward boundary tests for every 2026 closure across services and dated-folder routing. Document the calendar source and annual update workflow.

### 4. Remove hot-path database initialization and connection churn

A full diagnostic flow triggered 40 `init_db` calls and 61 query connections even with initialization bypassed; getters repeatedly initialize and open nested connections (`stock_expert/database.py:160-166` and getter paths).

**Actionable agent prompt:**

> Move initialization/migration to one CLI startup boundary and make getters migration-free. Introduce a request-scoped repository/data context that shares a connection and caches snapshot IDs, prices, market snapshots, weights, candidate outcomes, and adaptive exposure. Add instrumentation tests that cap initialization and query counts for the full routine while preserving atomic writes and branch-specific DB selection. Update architecture docs.

### 5. Honor Yahoo historical import end dates

Yahoo fetching always requests through now, then discards rows after the requested end date (`stock_expert/yahoo.py:36-44,225-240`). Closed historical ranges therefore over-fetch potentially years of data.

**Actionable agent prompt:**

> Change the Yahoo fetch API to accept explicit start/end epochs with only a small documented boundary buffer. Pass the requested interval from both import commands and add request-construction tests proving a past one-month import fetches only that interval. Preserve retry/backoff and timezone boundary correctness.

### 6. Add real point-in-time adaptive-policy integration coverage

Current service tests mock candidate outcomes and can inject future-dated rows, so they do not verify the storage/service anti-leakage boundary (`stock_expert/services.py:406-437`; `tests/test_services.py:606-630,864-898`).

**Actionable agent prompt:**

> Add temporary-SQLite integration tests with favorable pre-signal and contradictory post-signal outcomes, then call real `generate_picks`, `picks_output`, and `review_output` paths. Prove post-boundary evidence cannot change historical exposure and assert each service passes the intended `before_review_date`. Avoid mocks at the repository boundary.

## P2 — Medium priority

### Data integrity and business behavior

- Enforce snapshot ownership with foreign keys on `stocks`, `signals`, `picks`, and `market_snapshots`; validate parent date/source consistency.
- Require a documented minimum of complete, common sessions before adaptive top-3 selection; add coverage and effect-size/stability thresholds.
- Split missed-mover attribution into decisive cutoff reason and non-decisive context flags instead of overwriting breadth exclusion with setup penalty.
- Report companion-CSV join losses by source and warn/fail below a configured universe-retention threshold.
- Key `RankingContext` by database, snapshot, settings, and weight identity, or bind it explicitly to one immutable routine context.

**Actionable agent prompt:**

> Harden strategy and snapshot integrity: add snapshot-owner foreign keys via safe migrations; require complete common-session evidence and stability thresholds for adaptive exposure; make attribution fields non-overwriting; expose companion-file join retention; and make ranking cache identity include all immutable inputs. Add focused migration, sparse-evidence, attribution, join-loss, and stale-cache tests, then update feature/architecture docs.

### Security and ingestion resilience

- Restrict `--output` to an approved directory, prevent traversal/symlink clobbering, require `.csv`, and write atomically.
- Bound CSV/XLSX/HTTP sizes, rows, fields, decompression ratios, and ticker counts.
- Apply one strict BIST ticker validator to direct CLI and workbook input; reject control characters and malformed identifiers.
- Pin/bound the build dependency and use hash-locked release/CI constraints.

**Actionable agent prompt:**

> Harden all ingestion boundaries: resolve and contain output paths, reject symlink/reparse escapes, use atomic replacement, enforce resource limits before allocation/decompression, centralize ticker validation, and make build dependencies reproducible. Add traversal, absolute-path, symlink, overwrite, zip-bomb/oversize, ANSI/newline, Unicode, and dependency-verification tests. Document operational limits.

### Performance and verification

- Cache adaptive outcomes/exposure within one routine; current flow reloads them about seven times.
- Stream/batch Yahoo rows instead of retaining duplicate CSV and DB result sets; keep any concurrency small and backoff-aware.
- Add an index supporting `review_runs(review_date DESC)` and verify the query plan.
- Add an executable standard-library trace gate for the documented >=90% target.
- Add one compact persisted end-to-end test for `routine` and `midday-routine`, including rerun idempotency and dry-run boundaries.

**Actionable agent prompt:**

> Optimize and enforce the operator workflow: cache adaptive diagnostics per routine, stream/batch Yahoo imports, add and query-plan-test the review-date index, create a precise standard-library trace gate, and add a temporary-database end-to-end routine fixture covering snapshot, picks, review, weights, outcomes, reruns, holidays, and midday non-mutation. Update testing and performance documentation.

## Recommended execution order

1. Calendar closure hotfix.
2. Immutable snapshot/review behavior.
3. Legacy migration repair plus fixture coverage.
4. Database lifecycle/context refactor.
5. Yahoo interval correction.
6. Point-in-time integration tests.
7. P2 integrity, security, observability, and performance hardening.
