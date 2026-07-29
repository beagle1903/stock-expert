# Testing guidance

## Test strategy

The repository uses the standard-library `unittest` runner. Most meaningful behavior is covered at the command, service, and persistence layers.

## High-signal test areas

### CLI routing

`tests/test_cli.py` checks that:

- subcommands parse correctly
- `daily`, `picks`, and `review` route arguments to the right service functions
- `download-ohlcv` and `import-ohlcv-excel` forward all options
- `import-daily-csv` and `import-daily-folder` route to the import helpers
- `routine` and `midday-routine` differ in whether review is dry-run

### Service logic

`tests/test_services.py` is the largest behavior spec. It covers ranking, review idempotence, market-context policy, bucket diagnostics, and downside-risk behavior.

### Persistence and database behavior

`tests/test_database_prices.py` and `tests/test_review_persistence.py` cover snapshot run creation, latest snapshot selection, price history reads, review bundle persistence, candidate outcomes, dual pilot baskets, paired outcomes, and atomic rollback. `tests/test_pilot.py` covers the pure pilot decision policy.

### Configuration and imports

`tests/test_config.py` checks branch-aware database path selection and `.env` loading semantics. `tests/test_daily_csv.py` and `tests/test_yahoo.py` cover the import paths.

### Docs-stop hook

`tests/test_docs_stop_hook.py` exists because the repo has a Codex validation hook that blocks development changes without relevant documentation updates unless a deliberate `DOCS_NOT_NEEDED` reason is present.

## What to run

```powershell
& 'D:\miniconda3\python.exe' -m unittest discover -s tests -v
```

For trace coverage:

```powershell
New-Item -ItemType Directory -Force -Path .test_tmp\trace | Out-Null
& 'D:\miniconda3\python.exe' -m trace --count --summary --missing --coverdir .test_tmp\trace --module unittest discover -s tests
```
