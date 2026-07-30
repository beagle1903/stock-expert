# Testing guidance

## Test strategy

The repository uses the standard-library `unittest` runner rather than a heavier test framework. That matches the project’s standard-library-first approach and keeps the test setup light.

Most meaningful behavior is covered at the command, service, and persistence layers. When changing behavior, prefer to update the smallest layer that proves the rule, then run the full suite if the change crosses domains.

## High-signal test areas

### CLI routing

`tests/test_cli.py` checks that:

- subcommands parse correctly
- `daily`, `picks`, and `review` route arguments to the right service functions
- `download-ohlcv` and `import-ohlcv-excel` forward all options
- `import-daily-csv` and `import-daily-folder` route to the import helpers
- `routine` and `midday-routine` differ in whether review is dry-run

Use this test file when changing command names, arguments, or top-level output orchestration.

### Service logic

`tests/test_services.py` is the largest behavior spec. It covers:

- holiday and trading-session routing
- market context tagging and penalty behavior
- technical, quality, fundamental, and setup adjustments
- ranking and score composition
- review idempotence and dry-run behavior
- bucketed comparison output
- downside-risk and attribution behavior
- rolling cutoff and candidate diagnostics

Use this file when changing ranking, review, or market-context policy.

### Persistence and database behavior

`tests/test_database_prices.py` and `tests/test_review_persistence.py` cover:

- snapshot run creation
- per-date latest snapshot selection
- price history and mover reads
- review bundle persistence and review-run identity
- weights and candidate outcome storage
- dual pilot baskets, paired outcomes, terminal-state updates, and atomic rollback

`tests/test_pilot.py` covers the pure ten-session decision policy, including
compounding, incomplete pairs, rollback, promotion, and failure.

Use these tests when changing schema, migration, or write semantics.

### Configuration and imports

`tests/test_config.py` checks:

- branch-aware database path selection
- detached-head fallback behavior
- `.env` loading semantics
- repo-root path discovery

`tests/test_daily_csv.py` checks the daily CSV pipeline, and `tests/test_yahoo.py` checks the Yahoo import/download path.

### Docs-stop hook

`tests/test_docs_stop_hook.py` exists because the repo has a Codex validation hook that blocks development changes without relevant documentation updates unless a deliberate `DOCS_NOT_NEEDED` reason is present.

## What to run

For most changes, start with:

```powershell
& 'D:\miniconda3\python.exe' -m unittest discover -s tests -v
```

If you are only changing one area, run the matching focused tests first, then the full suite if the change affects shared workflow behavior.

For standard-library trace coverage:

```powershell
New-Item -ItemType Directory -Force -Path .test_tmp\trace | Out-Null
& 'D:\miniconda3\python.exe' -m trace --count --summary --missing --coverdir .test_tmp\trace --module unittest discover -s tests
```

Use the `stock_expert.*` summary rows, or count executed and `>>>>>>` lines in
the generated `stock_expert.*.cover` files for exact weighted coverage.

## Change-oriented guidance

- If a CLI output shape changes, update the CLI tests and any downstream expectations together.
- If review or ranking behavior changes, add or adjust service tests that prove the new rule at the business-logic level.
- If persistence changes, verify both write and read helpers; some tests intentionally ensure old and new snapshots coexist.
- If you alter the trading calendar or holiday logic, verify the date-routing tests carefully; those rules are explicit and not generated from generic holiday calendars.

## Source references

- CLI tests: `tests/test_cli.py`
- Service tests: `tests/test_services.py`
- Database tests: `tests/test_database_prices.py`, `tests/test_review_persistence.py`
- Config tests: `tests/test_config.py`
- Import tests: `tests/test_daily_csv.py`, `tests/test_yahoo.py`
- Hook test: `tests/test_docs_stop_hook.py`
