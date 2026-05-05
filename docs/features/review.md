# Feature: Review

- Previous-calendar-day performance
- Evaluates previous weekday signal-date picks against the requested realized market date
- Missed top movers
- Actionable vs non-actionable misses
- Data-driven weight adjustments from performance and actionable misses
- Counts a pick as a win only when return is at least 4%; smaller gains are treated as losses
- Persists each review run and pick-level return results
- Reuses an existing persisted review for the same signal/review date
- CSV-imported review returns use previous-close-to-latest price basis until a real open column/source is available
- Supports `--dry-run` and `--no-chase-penalty` for non-mutating strategy comparisons
- `routine` reports the normal persisted review after picks, then a no-chase-penalty dry-run review comparison
- `midday-routine` reports the dry-run review after picks without writing review rows
- No KAP inputs
