# Security Review

Scope: entire repository plus `git diff HEAD~5..HEAD`. Focused tests used isolated `.test_tmp` databases; live data was not modified.

## P1: A malformed numeric value can poison the active snapshot

**References:** `stock_expert/daily_csv.py:52-76`, `stock_expert/daily_csv.py:154-165`, `stock_expert/daily_csv.py:196-204`, `stock_expert/database.py:264-274`, `stock_expert/database.py:277-290`

`float()` accepts `NaN`, `INF`, and overflowing exponent values, but the importer checks only `ValueError`. SQLite binds Python `NaN` as `NULL`, so inserting it into a `REAL NOT NULL` column fails. The snapshot run is committed in a separate transaction before market and price rows are inserted.

Reproduction against a temporary database:

```text
IntegrityError: NOT NULL constraint failed: market_snapshots.last_price
latest_snapshot_id: 2
runs: [(1, valid), (2, nan)]
row_counts: [(1, 1)]
```

The failed empty run becomes the latest snapshot and masks the prior valid run. This is an availability and trading-data integrity failure at the primary CSV trust boundary.

**Suggested fix:** Reject all non-finite required and optional numbers with `math.isfinite`, enforce domain constraints such as nonnegative prices/volume, and perform snapshot creation plus both row inserts in one database transaction. Add a regression test proving a rejected import leaves the previous snapshot active.

## P2: “Relative” CLI paths permit arbitrary filesystem access

**References:** `stock_expert/cli.py:54-57`, `stock_expert/cli.py:75-87`, `stock_expert/yahoo.py:119-140`, `stock_expert/yahoo.py:207-218`, `stock_expert/daily_csv.py:112-119`, `stock_expert/daily_csv.py:232-242`

User-controlled `--output`, `--input`, `--data-dir`, and `--folder` values are joined without resolving and checking containment. Absolute paths discard `settings.base_dir`; `..` paths escape it. `download-ohlcv --output` can truncate/create any writable file, while import commands can read arbitrary matching files outside the repository.

**Suggested fix:** Centralize path resolution, reject absolute paths and traversal, and require resolved paths to remain under explicit roots (`data/` for imports and exports). Test absolute, `..`, symlink/junction, and mixed-separator cases.

## P2: Unbounded file and response parsing enables local memory exhaustion

**References:** `stock_expert/daily_csv.py:90-97`, `stock_expert/yahoo.py:45-46`, `stock_expert/yahoo.py:101-116`

All CSV rows are materialized, Yahoo bodies are read without a size cap, and an XLSX worksheet member is decompressed fully before XML parsing. A crafted CSV/XLSX or oversized response can exhaust memory; XLSX compression ratios make this practical with a small input file.

**Suggested fix:** Stream CSV processing, cap source/member/response sizes, inspect `ZipInfo.file_size` and compression ratio before extraction, and use bounded JSON/XML parsing where practical. Add oversized-input rejection tests.

## Residual Risks And Test Gaps

- SQL values are parameterized; reviewed dynamic identifiers/placeholders are internally generated. No SQL injection finding.
- No committed secrets or unsafe deserialization were found.
- SQLite foreign-key enforcement is not enabled, so future schema relationships need explicit integrity tests.
- Retry counts, delays, dates, and ticker lengths lack comprehensive bounds.
- Security-focused tests do not cover path containment, non-finite numbers, partial-import rollback, archive bombs, or oversized HTTP responses.

## Summary

One P1 and two P2 findings. Highest priority is making CSV import validation finite/domain-safe and atomic so malformed input cannot replace the active snapshot with an empty run.

Paths changed: `reviews/security-reviewer.md`
