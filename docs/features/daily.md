# Feature: Daily

- Market summary
- Key movers
- Uses latest imported CSV snapshot for the requested date
- `routine` and `midday-routine` import the current root CSV files before summary output
- Daily summary can surface a few signal-ready leaders from the ranked output when their technical/basic-analysis adjustments are supportive
- Daily CSV import skips obvious non-equity portfolio-management/fund rows unless explicitly allowlisted
- `review --date YYYY-MM-DD` reviews previous trading-day signal picks and missed movers for the requested review date
