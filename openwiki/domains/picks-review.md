# Picks and review domain

## What this domain covers

This is the strategy core of the application. It turns imported market snapshots into ranked picks, persists those picks, and then evaluates them on a later trading session.

## Pick generation

`stock_expert/services.py` builds signals from recent price history, then scores and ranks candidates. The score is centered on momentum and volume, with bounded technical, quality, and fundamental adjustments. The service layer also applies a capped setup penalty for bearish or stretched contexts.

A few practical rules matter:

- picks need enough imported history to produce meaningful momentum and volume signals
- low-liquidity candidates can be filtered out
- same-day overextension can incur a small penalty
- the routine reuses a request-scoped ranking cache so repeated reporting does not rerank the same signal date

## Selection and exposure

The controlled `bucketed-default-v1` pilot persists bucketed selection while active and keeps a complete score-ranked control basket. Bucketed uses `core_momentum`, `breakout_technical`, and `coverage_recovery`; score-ranked automatically resumes after rollback/failure.

The system can tighten exposure based on market breadth or rolling candidate evidence. That behavior is visible in the pick output and in the review comparison reports.

## Review behavior

Review evaluates previous signal-date picks against the requested realized market date. The review workflow persists:

- the review run summary
- per-pick realized returns
- candidate outcomes for cutoff analysis and attribution
- complete pilot baskets, pick outcomes, and paired arm summaries
- resulting weights

Important rules:

- a pick counts as a win only at 4% return or better
- rerunning the same signal/review date should reuse the persisted review instead of replacing candidate evidence
- dry-run review is used for `midday-routine`
- active pilot weights stay fixed, and only complete paired sessions advance the ten-session decision

## Market context policy

`services.py` includes explicit market-context tags for known shock sessions and low-liquidity sessions. Those tags influence selection policy and, in shock sessions, apply extra downside penalties.

## Source references

- `stock_expert/services.py`
- `stock_expert/signals.py`
- `stock_expert/models.py`
- `stock_expert/database.py`
- `tests/test_services.py`
- `tests/test_review_persistence.py`
