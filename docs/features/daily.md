# Feature: Daily

- Market summary
- Key movers
- Uses latest imported CSV snapshot for the requested date
- `routine` and `midday-routine` import the current root CSV files before summary output
- Daily CSV import skips obvious non-equity portfolio-management/fund rows unless explicitly allowlisted
- `review --date YYYY-MM-DD` reviews missed movers from the previous calendar day for now
