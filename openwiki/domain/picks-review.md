# Picks and review domain

## Summary

This repo’s business logic is built around three related outputs:

- a daily summary of market conditions and leaders
- a ranked pick list for the next trading session
- a review step that evaluates the previous signal-day picks against realized performance

The strategy is intentionally simple at the base level — momentum and volume — but adds bounded technical, quality, and fundamental adjustments plus a setup penalty so the score remains controlled.

## How candidates are built

`stock_expert/services.py` builds signals from the most recent price history and then turns them into ranked picks.

Key pieces:

- momentum uses short, medium, and moving-average trend signals from recent price bars
- liquidity is estimated from traded value versus a configured threshold
- volume spike compares the latest bar to a trailing average
- risk classification maps the combined signal strength into low, medium, or high
- technical, quality, and fundamental adjustments are bounded so they cannot dominate the base signal
- setup penalties reduce stretched or weakly supported candidates
- same-day chase penalties discourage late chasing after large daily gains

The ranking path is designed to keep the base signal dominant while still letting broader market context influence the final ordering.

## Pick selection policy

The default persisted pick list is score-ranked. Recent git history and current docs show a deliberate move toward preserving score-ranked default picks while exposing bucketed alternatives for analysis.

Important selection behavior:

- default exposure is capped and may shrink based on breadth and rolling evidence
- strong-breadth or strong-momentum candidates can be promoted through the score-ranked path
- bucketed selection remains available for comparison, with buckets such as `core_momentum`, `breakout_technical`, and `coverage_recovery`
- selection rows carry `selection_bucket` so later review can trace why a candidate was selected
- `routine` reports both the persisted score-ranked output and a score-ranked vs bucketed comparison

This means there are two related stories in the repo:

1. what the strategy actually persists as the live default
2. what alternative bucket composition says about possible exposure control

## Review logic

The review workflow evaluates the previous trading-day signal picks against the requested realized market date.

Highlights:

- reviews use the previous trading session, not a naive calendar day
- persisted review bundles are written as one transaction
- review runs are idempotent for the same signal/review date
- weights are updated from rolling performance, not from a single session shock
- candidate outcomes are persisted so later review can analyze rank cutoffs and near-miss behavior
- the repo treats returns under 4% as losses for win-rate purposes

The review output also includes attribution for reviewed picks and missed movers so operators can distinguish good misses from actual opportunities that were not selected.

## Market context and special routing

`services.py` includes explicit market-context logic for a few dates that were important enough to codify:

- political-shock sessions and follow-through dates
- low-liquidity half-holiday sessions

Those dates influence the selection policy and downside penalties. The implementation deliberately treats exact confirmed closures as exact dates, not recurring month/day rules.

## Important business rules to preserve

- Do not introduce future-data leakage.
- Keep outputs structured.
- Preserve the distinction between score-ranked default picks and bucketed diagnostics.
- Keep market holiday handling exact and user-confirmed.
- Review should stay idempotent and immutable once persisted.
- Historical rankings should use weights effective on or before the signal date.

## When changing this area

Start with `stock_expert/services.py`, then check `stock_expert/signals.py` and the service tests.

Useful tests:

- `tests/test_services.py` — primary behavior coverage for ranking, review, market context, and diagnostics
- `tests/test_cli.py` — command-level routing and output shape
- `tests/test_review_persistence.py` and `tests/test_database_prices.py` — persistence expectations around review and snapshots

## Source references

- Ranking and review orchestration: `stock_expert/services.py`
- Signal math: `stock_expert/signals.py`
- Session routing: `stock_expert/trading_calendar.py`
- Business notes: `docs/features/picks.md`, `docs/features/review.md`, `docs/features/daily.md`