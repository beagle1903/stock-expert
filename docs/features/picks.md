# Feature: Picks

- Ranked stocks
- Signal breakdown
- Risk label
- Intraday horizon
- Uses momentum and volume only
- Needs multiple imported days for non-zero momentum and volume signals
- Applies a small score penalty to overextended same-day movers above `+8%`
- Uses `signal_date` market data to generate picks for the next weekday `target_trade_date`
