# Feature: Picks

- Ranked stocks
- Signal breakdown
- Risk label
- Intraday horizon
- Uses momentum and volume only
- Needs multiple imported days for non-zero momentum and volume signals
- Applies a small score penalty to overextended same-day movers above `+8%`
- Uses the latest `signal_date` snapshot to generate picks for the next weekday `target_trade_date`
- Multiple same-day imports can coexist; date-based picks use the latest snapshot
- Supports `--dry-run` and `--no-chase-penalty` for safe comparison runs
- Daily routine reports no-chase-penalty dry-run picks beside normal picks
