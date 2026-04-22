# Feature: Picks

- Ranked stocks
- Signal breakdown
- Risk label
- Intraday horizon
- Base score uses momentum and volume
- Adds bounded soft boosts from daily/weekly technical labels and basic-analysis quality fields
- Needs multiple imported days for non-zero momentum and volume signals
- Applies a small score penalty to overextended same-day movers above `+8%`
- Uses the latest `signal_date` snapshot to generate picks for the next weekday `target_trade_date`
- Multiple same-day imports can coexist; date-based picks use the latest snapshot
- Supports `--dry-run` and `--no-chase-penalty` for safe comparison runs
- `routine` reports normal persisted picks plus a no-chase-penalty dry-run comparison after the live CSV import
- `midday-routine` reports normal picks after the live CSV import
