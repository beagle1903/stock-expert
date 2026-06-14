# Business Logic Review

Scope: entire codebase plus `git diff HEAD~5..HEAD`, with emphasis on BIST session routing, snapshot and review alignment, strategy/exposure semantics, persistence integrity, and operator-facing explanations.

## P1 Findings

### P1: Dated-folder imports route across exchange holidays as ordinary weekdays

- Evidence: `stock_expert/daily_csv.py:225-229` implements a separate `_previous_weekday()` that skips weekends only. `stock_expert/daily_csv.py:232-244` uses it to derive the signal snapshot date from a dated target-trade folder.
- Reproduction: for target folder date `20260601`, the folder helper returns `2026-05-29`, while the canonical holiday-aware `stock_expert/services.py:117-121` returns `2026-05-26`. May 27-29 are explicitly closed in `stock_expert/services.py:44-52`.
- Impact: importing `data/20260601` labels the snapshot as a closed exchange date. Subsequent picks/reviews can fail to find the real May 26 signal snapshot or evaluate the wrong signal/review pair.
- Suggested fix: remove the duplicate helper and use one shared trading-calendar function for both services and folder imports. Add a regression test for `20260601 -> 2026-05-26` and other exact holiday boundaries.

### P1: Rerunning an idempotent review can rewrite historical candidate evidence using future weights

- Evidence: ranking uses the globally latest weights without an `as_of` bound at `stock_expert/services.py:252-263` and `stock_expert/database.py:455-471`. Every persisted review, including an existing review, recomputes candidates and unconditionally replaces outcomes at `stock_expert/services.py:906-907`, `stock_expert/services.py:965-990`, and `stock_expert/database.py:503-545`.
- Impact: after later reviews change weights, rerunning an old review can change historical ranks, bucket membership, and cutoff diagnostics while leaving the original `review_runs` row unchanged. The resulting evidence is not point-in-time reproducible and can create look-ahead contamination in strategy decisions.
- Suggested fix: persist the exact ranked candidate set and active weights/snapshot identity on first review, then never replace it for an existing review. Alternatively, query weights effective on or before the signal date and bind outcomes to the original signal snapshot. Add a test that inserts later weights, reruns an old review, and asserts byte-for-byte stable outcomes.

### P1: Score-ranked versus bucketed diagnostics compare different exposure sizes

- Evidence: score-ranked picks apply breadth caps at `stock_expert/services.py:345-365`, reducing exposure to 2 or 3 names. Bucketed picks always default to `settings.default_pick_count` at `stock_expert/services.py:496-506`. Both the live comparison and persisted candidate outcomes compare these unequal baskets at `stock_expert/services.py:714-740` and `stock_expert/services.py:984-990`.
- Impact: in weak markets, diagnostics attribute performance differences to selection strategy even though score-ranked may hold two names and bucketed five. This is not an apples-to-apples selection comparison and can produce misleading evidence for promoting bucketed selection.
- Suggested fix: compute the effective breadth cap once for the signal snapshot and pass the same `pick_count` to both strategies. If unequal exposure is intentional, label it explicitly and report both equal-count and policy-count comparisons. Add a weak-breadth comparison test.

## P2 Findings

### P2: Miss attribution ignores the active breadth-adjusted cutoff

- Evidence: `_attribution_for_pick()` labels ranks `<= settings.default_pick_count` as `inside_top_pick_cutoff` at `stock_expert/services.py:790-805`, while actual selection may be capped at two or three names by `stock_expert/services.py:368-393`.
- Impact: on weak-breadth sessions, ranks 3-5 can be described as inside the cutoff even though exposure policy deliberately excluded them. Operators receive the wrong reason for a miss.
- Suggested fix: pass the effective signal-date pick cap into attribution and distinguish `excluded_by_breadth_cap` from `below_score_cutoff` and `penalized_by_setup_context`. Test rank 3 under a two-pick cap.

### P2: Half-holiday context is treated as political-shock policy

- Evidence: all `MARKET_CONTEXT_NOTES` dates trigger `shock_mode_penalty` and political-shock interpretation at `stock_expert/services.py:54-79`; all tagged dates also receive shock penalties at `stock_expert/services.py:86-103`. Therefore isolated `2026-05-26` reports `half_holiday_low_liquidity` but selects `shock_mode_penalty` and political-shock wording.
- Impact: a liquidity/session-duration condition is conflated with an exogenous shock. Ranking changes and operator explanations do not match the tag's business meaning.
- Suggested fix: model context tags with explicit policy metadata, applying shock penalties only to shock dates and a separate half-day/liquidity policy to May 26. Add an isolated half-holiday context test.

## Residual Risks And Test Gaps

- Holiday coverage is a hard-coded 2026 subset; future closures require explicit maintenance and boundary tests.
- Candidate cutoff recommendations use pooled per-stock returns and only require total row count to match session count; no confidence or per-session completeness guard exists.
- No integration test proves repeated same-day imports preserve the intended final action snapshot through next-session review.
- Full suite passed: 56 tests in 3.498 seconds.

## Summary

No P0 findings. Three P1 issues can corrupt date alignment or strategy evidence; two P2 issues misstate selection rationale/context.

Paths changed: `reviews/business-logic-reviewer.md`.
