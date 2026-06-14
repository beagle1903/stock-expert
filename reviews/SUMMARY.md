# Parallel Code Review Summary

Scope: full repository and `git diff HEAD~5..HEAD`, reviewed independently for security, architecture, test coverage, performance, and business logic.

Verification: all 56 unit tests passed. Reviewers used isolated temporary databases and did not modify live data or production code.

Synthesis method: duplicate findings were merged by root cause, severity was normalized by user/data-integrity impact, and cited locations were checked against the current working tree.

## P0

No P0 findings.

## P1

### 1. Make daily CSV snapshot publication validated and atomic

Malformed non-finite values can fail after `snapshot_runs` is committed, leaving an empty run as the latest snapshot. The same multi-transaction design permits other partial imports.

References: `stock_expert/daily_csv.py:52-76`, `stock_expert/daily_csv.py:196-204`, `stock_expert/database.py:264-290`.

**Actionable agent prompt**

> Validate every imported numeric field with `math.isfinite` and appropriate domain constraints. Add one transaction-scoped database API that creates the snapshot run and inserts market/price rows atomically. Ensure failed imports leave the previous latest snapshot active. Add fault-injection and `NaN`/`INF` regression tests.

### 2. Preserve point-in-time historical review evidence

Historical ranking uses globally latest weights, rolling calculations can include later reviews, and reruns replace candidate outcomes. Old evidence can therefore change after future data or code changes.

References: `stock_expert/services.py:252-264`, `stock_expert/services.py:894-991`, `stock_expert/database.py:455-545`, `stock_expert/database.py:584-597`.

**Actionable agent prompt**

> Add date-bounded weight and review queries, persist the signal snapshot, weight version, and strategy version used by each review, and never replace candidate outcomes for an existing review. Add tests that insert later weights/reviews/snapshots and prove an older review remains byte-for-byte stable.

### 3. Persist each review as one idempotent transaction

Weights, review rows, results, and candidate outcomes are written in separate transactions, while `review_runs` lacks a database uniqueness constraint.

References: `stock_expert/services.py:965-991`, `stock_expert/database.py:89-131`, `stock_expert/database.py:503-653`.

**Actionable agent prompt**

> Implement `persist_review_bundle()` using one SQLite transaction. Add `UNIQUE(as_of_date, review_date)`, link outcomes to `review_run_id`, and handle conflicts by loading the existing bundle. Add rollback tests at every write boundary and a concurrent idempotency test.

### 4. Unify holiday-aware trading-session routing

The dated-folder importer skips weekends only. For `20260601` it stores `2026-05-29`, although the correct prior BIST session is `2026-05-26`.

References: `stock_expert/daily_csv.py:225-244`, `stock_expert/services.py:44-52`, `stock_expert/services.py:117-128`.

**Actionable agent prompt**

> Move trading-session calculations and exact closures into a dependency-neutral calendar module used by services and import adapters. Add folder-import tests for weekends, May 1, 2026, and the May 27-29, 2026 closure window, including `20260601 -> 2026-05-26`.

### 5. Compare selection strategies at equal exposure

Breadth caps reduce score-ranked picks to two or three names, while bucketed diagnostics still use five, confounding selection quality with exposure.

References: `stock_expert/services.py:345-393`, `stock_expert/services.py:496-506`, `stock_expert/services.py:714-740`.

**Actionable agent prompt**

> Compute one effective signal-date pick cap and pass it to both score-ranked and bucketed selection. Report policy-count and equal-count comparisons separately if both are needed. Add weak-breadth tests proving the compared baskets use the intended exposure.

### 6. Eliminate repeated ranking work in `routine`

The same signal-date ranking is rebuilt up to eight times, repeatedly loading history, snapshots, prices, and weights.

References: `stock_expert/cli.py:192-207`, `stock_expert/services.py:138-160`, `stock_expert/services.py:252-333`, `stock_expert/services.py:719-727`, `stock_expert/services.py:894-985`.

**Actionable agent prompt**

> Introduce a request-scoped ranking context computed once per signal date and reused by daily output, picks, persisted review attribution, comparisons, and diagnostics. Preserve standalone command behavior. Add a routine-level call-count regression test and latency benchmark.

### 7. Remove per-row SQLite initialization from Yahoo imports

A 500-ticker by 30-day import performs 15,000 snapshot lookups, each reopening SQLite and running schema initialization/migration checks.

References: `stock_expert/database.py:147-152`, `stock_expert/database.py:264-321`, `stock_expert/yahoo.py:141-190`, `stock_expert/yahoo.py:221-266`.

**Actionable agent prompt**

> Resolve or create snapshot IDs once per distinct date using one connection and transaction, map rows in memory, and bulk upsert them. Move schema initialization to application startup. Add a test asserting snapshot lookup count scales with distinct dates, not OHLCV rows.

## P2

### Persistence and operational safety

- Add foreign keys and deliberate cascade/restrict behavior for snapshot/review ownership.
- Fail closed or use an isolated database for detached HEAD and git lookup failures.
- Add indexes for latest snapshot, review lookup, and candidate diagnostic access paths.

**Actionable agent prompt**

> Add migrations for foreign keys, review ownership, and indexes on `snapshot_runs(snapshot_date, id DESC)`, `review_runs(as_of_date, review_date, id DESC)`, and `candidate_outcomes(review_date DESC, candidate_rank)`. Enable `PRAGMA foreign_keys = ON`, test orphan rejection/query plans, and make unknown git state select an isolated database.

### Input and resource hardening

- CLI path arguments can escape intended roots.
- CSV, XLSX, and Yahoo responses are parsed without practical size bounds.
- Yahoo downloads retain duplicate full-size row collections.

**Actionable agent prompt**

> Centralize root-contained path resolution; reject absolute paths, traversal, and junction escapes. Stream CSV/download output, cap HTTP and archive-member sizes/compression ratios, and batch database writes. Add traversal, oversized payload, archive-bomb, and bounded-memory tests.

### Operator-facing business semantics

- Miss attribution uses the default five-pick cutoff instead of the active breadth cap.
- Half-holiday context receives political-shock penalties and wording.

**Actionable agent prompt**

> Pass the effective breadth cap into attribution and emit `excluded_by_breadth_cap` where appropriate. Replace generic context-note handling with typed policy metadata so half-holiday liquidity policy is distinct from political-shock policy. Add focused tests for both cases.

### Coverage gaps

- Yahoo ingestion has no direct tests.
- Direct CLI command routing and invalid-date exits are lightly covered.
- No performance budget or representative large-history query-plan test exists.

**Actionable agent prompt**

> Add mocked Yahoo parser/retry/import tests, direct CLI error-path tests, breadth boundary cases, and representative performance/query-plan checks. Keep tests isolated from live SQLite and network access.

## Source Reports

- `reviews/security-reviewer.md`
- `reviews/architecture-reviewer.md`
- `reviews/test-coverage-reviewer.md`
- `reviews/performance-reviewer.md`
- `reviews/business-logic-reviewer.md`

DOCS_NOT_NEEDED: This task produced review artifacts only; production behavior and project documentation were not changed.
