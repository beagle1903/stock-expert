# Feature: Daily

- Market summary
- Key movers
- Uses latest imported CSV snapshot for the requested date
- `routine` imports the current root CSV files before summary output
- Daily summary can surface a few signal-ready leaders from the ranked output when their technical/basic-analysis adjustments are supportive
- Daily CSV import skips obvious non-equity portfolio-management/fund rows unless explicitly allowlisted
- Required numeric fields reject non-finite and invalid price/volume values
- Daily CSV import detects comma- or dot-decimal bundles from the percentage column and applies that locale consistently to prices, percentages, and abbreviated fundamentals
- Company-to-ticker resolution prefers a validated source symbol/code when the live CSVs provide one (`Kod`, `Sembol`, `Symbol`, `Code`, `Ticker`, or `Hisse Kodu` after header normalization). Values are trimmed, uppercased, stripped of a trailing `.IS`, and accepted only as 3-6 character codes starting with a letter
- `ticker_map.csv` remains the collision-free company-name fallback when a source symbol is missing or invalid; unmapped rows are still skipped and never become fabricated prefix tickers
- A company with more than one distinct valid source symbol across the four tables is skipped as a conflict. If two companies resolve to the same ticker, the later collision is skipped. Conflict, invalid, and unmapped names reuse existing mapping-failure persistence so Snapshots can show them. Import JSON keeps `fallback_count` as the unmapped skip total and reports `ticker_map_fallback_count` plus `source_map_disagreement_count` when a source code differs from the map
- Company-to-ticker resolution also uses collision-free aliases from the ticker code, company name, matched name, and removable corporate suffixes when falling back to the map
- Live-size imports with at least 500 source rows must resolve at least 75% of eligible rows to distinct tickers before any snapshot is persisted
- Snapshot metadata, market rows, price rows, and captured provenance (coverage, skip counts, mapping-failure names) commit atomically; failed imports leave the previous latest snapshot active. Older non-CSV `create_snapshot_run` rows stay `not_captured`. The Evidence Console Snapshots view is read-only lineage, not a daily command.
- Dated-folder imports use the same holiday-aware trading calendar as picks and review
- `review --date YYYY-MM-DD` reviews previous trading-day signal picks and missed movers for the requested review date
