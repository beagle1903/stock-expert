# Feature: Download OHLCV

- Yahoo is an optional secondary path. It is not part of `routine`.
- CLI tickers are alphanumeric BIST codes (optional `.IS`); invalid codes are reported and skipped.
- Fetch windows honor `--days` or Excel `--start-date`/`--end-date` with a five-day start buffer and inclusive end.
- Retries cover HTTP 429 (`Retry-After` or backoff), transient network errors, and malformed JSON. Empty, error, or zero-bar chart payloads fail that ticker without retry.
- CSV export stays under `data/` and cannot overwrite `fiyat.csv`, `performans.csv`, `teknik.csv`, or `temel.csv`.
- A download that produces zero rows, or any ticker failure while a Yahoo CSV already exists, leaves that file in place and does not write SQLite. `rows_written` is the count actually published, so a preserved file reports `0`.
- `--import-db` / Excel DB import publishes source-owned `yahoo_ohlcv` snapshot runs. Those rows do not mutate daily-CSV snapshots.
- Operational reads use an allow-list: only `daily_csv` and `legacy` snapshot runs feed ranking, selection, review pricing, and price-history (signal) windows. Every other label (`yahoo_ohlcv`, `yahoo_history_browser`, any future repair label) is non-operational by default, even on a date with no daily-CSV run. The shared filter is `_OPERATIONAL_SNAPSHOT_SQL` in `stock_expert/database.py`. Snapshot history in the Evidence Console still lists those runs.
- Partial ticker failures still export/import only successful rows; live CSVs are never touched.
- Use this path for diagnostics or historical backfill. Trusted operator data remains the four Investing.com CSVs plus `routine`.
