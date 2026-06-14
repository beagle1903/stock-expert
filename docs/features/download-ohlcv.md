# Feature: Download OHLCV

- Yahoo symbol normalization, null-row filtering, retry behavior, CSV export, optional SQLite import, Excel ticker parsing, date filtering, batching, and failure reporting have direct unit coverage

- Fetch Yahoo Finance OHLCV
- Export CSV
- Optional SQLite import
- Retry with backoff on `HTTP 429`
- Progress lines during download
