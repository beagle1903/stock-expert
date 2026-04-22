# Feature: Review

- Previous-calendar-day performance
- Evaluates previous weekday signal-date picks against the requested realized market date
- Missed top movers
- Actionable vs non-actionable misses
- Weight adjustments
- Persists each review run and pick-level open-to-close results
- Supports `--dry-run` and `--no-chase-penalty` for non-mutating strategy comparisons
- `routine` reports the normal persisted review after picks, then a no-chase-penalty dry-run review comparison
- `midday-routine` reports the dry-run review after picks without writing review rows
- No KAP inputs
