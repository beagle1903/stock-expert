# Fade-Then-Rechase Penalty Design

Requirement ticket: [GitHub issue #21](https://github.com/beagle1903/stock-expert/issues/21).
Branch: `codex/fade-then-rechase-penalty`.

## Goal

Stop re-selecting names that spiked ~+10% one or two sessions ago and are
being chased again after that spike is no longer immediate continuation.
Stop treating deep, setup-penalized limit-up misses as strategy failures.

## Current Gap

Same-day chase and `setup_penalty` only see today's snapshot. Ranking does
not use prior-session close returns. Missed-mover `selection_note` overwrites
breadth/cutoff notes with `penalized_by_setup_context`. UNLU-class +10% names
at rank 200+ stay `actionable`/`not_selected_by_score`.

## Rule

Use price bars available at signal time (`get_recent_price_history`). Build
close-to-close percent returns for the two sessions **before** `as_of`.

- If the **latest prior** session is already ~+10% (`>= 9.0`), do not add this
  penalty (KARSN-class immediate continuation).
- If an **older** prior session in that window is ~+10%, subtract a fade-then-
  rechase score penalty (EPLAS/AKFYE class). Add a small extra when the
  signal-date exposure cap is already below 5.
- Do not change base momentum/volume scoring, pilot baskets, or reviewed rows.

## Miss taxonomy

- `reason=setup_penalized_limit_up` and `non_actionable` when realized move
  `>= 9%`, `setup_penalty >= 0.05`, and `candidate_rank > 50`.
- `selection_note=near_cutoff` when rank is `<= 20` and above the active pick
  cap. This note wins over generic setup overwrite.
- `excluded_by_breadth_cap` still wins over generic `penalized_by_setup_context`.
- Existing reviews stay `INSERT OR IGNORE`; no backfill.

## Tests

Unit tests for the penalty (continuation vs fade-then-rechase vs reduced
breadth) and miss tags. Existing attribution tests stay valid except where
priority is intentionally fixed.
