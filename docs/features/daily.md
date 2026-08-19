# Feature: Daily

- Market summary
- Key movers
- Uses latest imported CSV snapshot for the requested date
- `routine` and `midday-routine` import the current root CSV files before summary output
- Daily summary can surface a few signal-ready leaders from the ranked output when their technical/basic-analysis adjustments are supportive
- Daily CSV import skips obvious non-equity portfolio-management/fund rows unless explicitly allowlisted
- Required numeric fields reject non-finite and invalid price/volume values
- Daily CSV import detects comma- or dot-decimal bundles from the percentage column and applies that locale consistently to prices, percentages, and abbreviated fundamentals
- Company-to-ticker resolution uses collision-free aliases from the ticker code, company name, matched name, and removable corporate suffixes
- Live-size imports with at least 500 source rows must resolve at least 75% of eligible rows to distinct tickers before any snapshot is persisted
- Snapshot metadata, market rows, and price rows commit atomically; failed imports leave the previous latest snapshot active
- Dated-folder imports use the same holiday-aware trading calendar as picks and review
- `review --date YYYY-MM-DD` reviews previous trading-day signal picks and missed movers for the requested review date
