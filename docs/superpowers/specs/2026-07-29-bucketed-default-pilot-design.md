# Bucketed-Default Pilot Design

## Goal

Run a controlled ten-session pilot in which bucketed selection is the persisted
default basket, score-ranked selection is a complete control basket, and the
system automatically returns to score-ranked selection if the evidence turns
against bucketed selection.

## Scope

- Keep the current candidate scoring formula and the current
  momentum/volume weights unchanged while the pilot is active.
- Keep the existing breadth-derived pick-count cap for both strategy arms.
- Persist every selected score-ranked and bucketed pick at signal time.
- Persist every available realized pick outcome and paired session summary at
  review time.
- Make bucketed picks the rows exposed through the existing `picks` table while
  the pilot is active.
- Do not add dependencies, order execution, portfolio sizing, or frontend
  controls.

## Alternatives Considered

1. Add pilot-specific persistence. This is the selected approach because it
   records complete baskets even when bucketed picks fall outside the top 50
   candidate rows.
2. Reuse `candidate_outcomes`. This is rejected because that table is a bounded
   ranking diagnostic and cannot guarantee complete bucketed-basket evidence.
3. Keep bucketed selection shadow-only. This is rejected because it would not
   test bucketed selection as the operational default.

## Architecture

`stock_expert/pilot.py` owns the pure policy: thresholds, compounded-return
calculation, session-win counting, terminal-state evaluation, and mapping pilot
state to the operational strategy. It has no database or CLI dependency.

`stock_expert/database.py` owns three new SQLite tables and their transactional
operations:

- `strategy_pilot_state`: one durable state row for
  `bucketed-default-v1`, including status, start date, completed paired
  sessions, bucketed session wins, compounded returns, edge, fixed pilot
  weights, and decision reason.
- `strategy_pilot_picks`: both immutable signal-time baskets, keyed by signal
  snapshot, strategy, and ticker. Review fields are nullable until the
  corresponding market session is evaluated.
- `strategy_pilot_sessions`: one summary per signal snapshot and strategy,
  including pick count, evaluated count, wins, average return, and completeness.

`stock_expert/services.py` builds score-ranked and bucketed baskets once from
the same cached ranking and breadth cap. Persisted `picks` use the strategy
selected by the pilot state; both baskets are stored for evidence. A normal
review supplies target prices to the same review transaction that currently
persists the review bundle, so pilot outcomes cannot be partially committed.

`stock_expert/cli.py` starts the pilot before the first full routine review.
Within a full routine, it computes the persisted review before persisting the
new signal-date picks, while retaining the existing human-readable output
order. This lets a rollback triggered by the just-completed session affect the
next basket without a one-session delay. `midday-routine` remains non-mutating.

## Pilot Policy

- Pilot name: `bucketed-default-v1`.
- Active arm: `bucketed`; control arm: `score_ranked`.
- Planned evidence window: 10 complete paired sessions.
- A paired session counts only when both arms have at least one pick and every
  pick in both arms has a realized price outcome.
- A bucketed session win means its equal-weight average return is strictly
  greater than the score-ranked average return.
- Cumulative return for each arm compounds its equal-weight daily basket
  returns: `product(1 + session_return) - 1`.
- Immediate rollback: after any complete paired session, bucketed compounded
  return minus score-ranked compounded return is less than or equal to `-0.03`.
- Promotion after session 10: bucketed wins at least 6 paired sessions and its
  compounded edge is at least `0.03`.
- Failure after session 10: either promotion condition is not met.
- Operational selection is bucketed for `active` and `promoted`; it is
  score-ranked for `rolled_back` and `failed`.
- Terminal states never reopen or change when later diagnostic sessions are
  recorded.

## Weight Isolation

The state row captures the momentum and volume weights effective when the pilot
starts. While status is `active`, normal reviews persist the same weights
instead of applying rolling weight adjustments. The session that reaches a
terminal decision is therefore evaluated under the fixed pilot weights.
Existing rolling-weight behavior resumes only after the pilot is terminal.

## Data Flow

1. A full routine imports the current snapshot and initializes the pilot state
   if it does not exist.
2. The current market summary computes and caches the signal-date ranking using
   the fixed pilot weights.
3. The review evaluates the previous signal snapshot. If pilot baskets exist,
   it updates their outcomes, writes paired session summaries, and updates the
   state atomically with the existing review bundle.
4. The pick step builds breadth-matched score-ranked and bucketed baskets from
   the cached ranking, selects the operational arm from the updated state,
   persists that arm to `picks`, and stores both pilot baskets.
5. JSON output exposes the selected strategy and current pilot state.

## Idempotency and Error Handling

- Basket writes replace only rows for the same pilot and signal snapshot.
- Review reruns preserve the original review and pilot evidence.
- Missing prices produce an incomplete session that is persisted for
  visibility but does not advance the pilot counter.
- Any pilot-outcome persistence failure rolls back the review run, weights,
  pick results, candidate outcomes, pilot outcomes, session summaries, and
  state update together.
- Schema creation and column/table upgrades remain safe on existing databases.

## Tests

- Pure policy tests cover active, rollback, promotion, failure, strict
  session-win comparison, and compounded-return arithmetic.
- Database tests cover dual-basket persistence, complete and incomplete
  outcomes, idempotency, state updates, and atomic rollback.
- Service tests prove both arms use the same breadth cap, bucketed is persisted
  while active, score-ranked is persisted after rollback/failure, pilot weights
  remain fixed, and JSON exposes pilot state.
- CLI tests prove a full routine reviews before persisting current picks while
  keeping the output sections stable, and that `midday-routine` stays dry-run.
- The full standard-library test suite, trace coverage check, `git diff
  --check`, and a branch-database smoke run are required before handoff.
