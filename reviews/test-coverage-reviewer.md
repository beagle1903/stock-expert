# Test Coverage Review

Scope: entire repository, with emphasis on `git diff HEAD~5..HEAD`.

Verification: `D:\miniconda3\python.exe -m unittest discover -s tests -v` passed all 56 tests in 3.178s. `coverage.py` is not installed, so coverage was assessed by code/test inspection.

## P0

No P0 findings.

## P1 Findings

### P1: Dated-folder imports do not test exchange holidays and currently route June 1 incorrectly

- Evidence: `stock_expert/daily_csv.py:225-239` uses a weekend-only `_previous_weekday`, while the canonical helper in `stock_expert/services.py:117-128` skips confirmed closures. Direct inspection produced `2026-05-29` from the folder helper versus the correct `2026-05-26` from the service helper for target date `2026-06-01`. `tests/test_daily_csv.py:18-186` has no folder-import test.
- Impact: `import-daily-folder --folder data/20260601` can persist the snapshot under a closed exchange date, breaking pick/review date alignment.
- Suggested fix: Add parameterized folder-import tests for weekends, `2026-05-01`, and the `2026-05-27` through `2026-05-29` closure. Reuse one holiday-aware trading-date helper in both import and service paths.

### P1: Review rerun tests miss mutable historical candidate outcomes

- Evidence: `stock_expert/services.py:965-990` reuses an existing review run but still unconditionally calls `replace_candidate_outcomes`. `tests/test_services.py:410-428` asserts only that weights/review rows are not reinserted; `tests/test_services.py:430-458` tests only first-write outcome persistence.
- Impact: rerunning an old review after ranking logic or source snapshots change can silently rewrite historical diagnostic evidence while retaining the original review ID.
- Suggested fix: Add an integration test that persists a review, changes recomputed candidates, reruns the same date, and asserts candidate outcomes remain byte-for-byte unchanged. Gate outcome persistence to first review creation or version diagnostic methodology explicitly.

### P1: No failure-injection test protects review persistence atomicity

- Evidence: `stock_expert/services.py:967-990` writes weights, review rows, and candidate outcomes through separate transactions (`stock_expert/database.py:378-392`, `601-653`, `503-545`). Existing tests mock successful calls but never raise between them.
- Impact: a failure after weight insertion can leave strategy weights advanced without a matching review; a later failure can leave a review without diagnostics.
- Suggested fix: Add SQLite integration tests that inject failures after each write boundary and assert rollback/no partial state. Implement one transaction-scoped persistence operation for the review unit of work.

### P1: Daily CSV import has no partial-write rollback test

- Evidence: `stock_expert/daily_csv.py:196-204` creates a snapshot run, writes market snapshots, then writes prices in separate transactions. `tests/test_daily_csv.py:68-185` covers successful, malformed, unmapped, and column-migration cases only.
- Impact: a price-write failure can leave the newest snapshot selected with incomplete data, causing empty signals/picks or inconsistent summaries.
- Suggested fix: Inject failures into each persistence step and assert no latest partial snapshot remains. Persist snapshot metadata, market snapshots, and prices in one transaction.

## P2 Findings

### P2: Yahoo secondary ingestion is effectively untested

- Evidence: `stock_expert/yahoo.py:29-280` contains symbol normalization, response parsing, retries, XLSX parsing, CSV output, and SQLite import. No test imports or patches `stock_expert.yahoo`.
- Impact: API shape changes, retry off-by-one errors, malformed workbooks, and DB import regressions can ship unnoticed.
- Suggested fix: Add mocked tests for null OHLCV rows, HTTP 429/`Retry-After`, transient retry exhaustion, malformed Yahoo payloads, minimal XLSX parsing, date filtering, and optional DB import.

## Residual Risks / Test Gaps

- No concurrency test verifies single review creation; `review_runs` has no uniqueness constraint for `(as_of_date, review_date)`.
- CLI tests cover only `routine` and `midday-routine`; direct command routing and invalid-date/error exits are untested.
- Breadth tests cover `<0.2` and exactly `0.2`, but not exactly `0.3`, empty universes, or custom pick caps.

## Summary

The suite is green, but recent persistence and diagnostic features lack rollback and rerun-integrity coverage. The holiday-folder mismatch is directly reproducible and should be addressed first.
