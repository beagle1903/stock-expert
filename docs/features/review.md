# Feature: Review

- Previous-calendar-day performance
- Evaluates previous weekday signal-date picks against the requested realized market date
- Missed top movers
- Actionable vs non-actionable misses
- Data-driven weight adjustments from performance and actionable misses
- Reports `no_prior_picks` when there are no persisted signal-date picks to review, so zero performance is not mistaken for strategy evidence
- Includes reviewed-pick and missed-mover attribution from recomputed signal-date ranks, signal components, boosts, and setup penalty context
- Reviewed persisted picks can include `selection_bucket`, allowing later bucket-level performance checks
- Counts a pick as a win only when return is at least 4%; smaller gains are treated as losses
- Persists each review run and pick-level return results
- Reuses an existing persisted review for the same signal/review date
- CSV-imported review returns use previous-close-to-latest price basis until a real open column/source is available
- Supports `--dry-run` and `--no-chase-penalty` for non-mutating strategy comparisons
- `routine` reports the normal persisted review after picks, then a no-chase-penalty dry-run review comparison
- `midday-routine` reports the dry-run review after picks without writing review rows
- No KAP inputs
