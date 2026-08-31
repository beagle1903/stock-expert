# Strategy Evidence Lab Plan

Status: implemented on `codex/strategy-evidence-lab` on 2026-08-31.

## Goal

Turn immutable strategy evidence into a read-only dashboard for comparing the
score-ranked control with the bucketed variant and investigating the persisted
conditions behind their outcomes.

## Product Scope

- Add a Strategy Evidence Lab to the existing Diagnostics screen.
- Support the latest 5, 10, 20, or all persisted review windows.
- Compare only complete paired pilot sessions while keeping incomplete and
  unpaired sessions visible.
- Show pilot thresholds, as-of status, complete-session count, session wins,
  compounded returns, edge, and terminal decision.
- Show cutoff analysis, rank bands, setup-penalty evidence, and signal-snapshot
  breadth for the selected window.
- Provide explicit empty, partial, incomplete, and unavailable states.

## Evidence Boundary

- Review windows are selected from persisted `review_runs`.
- Candidate diagnostics use only `candidate_outcomes` owned by those reviews.
- Strategy comparisons use immutable `strategy_pilot_sessions`; basket
  membership is never recomputed.
- Historical pilot status is reconstructed only from stored sessions at or
  before the selected window end.
- Breadth is calculated from the exact `review_runs.signal_snapshot_id` stocks,
  never from a later or latest snapshot.

## Implementation Slices

1. Add bounded read queries and a typed `/api/strategy-evidence` response.
2. Add frontend domain/repository state for selectable evidence windows.
3. Build responsive pilot, comparison, cutoff, rank-band, breadth, and
   setup-penalty panels inside the Evidence Console.
4. Cover metric mapping, future-data exclusion, exact-snapshot breadth, and key
   empty/incomplete states in Python and frontend tests.
5. Run full tests/build, browser QA, and update feature/context/task memory.

## Review Hardening

- Use the final selected signal date, not its later review date, when deciding
  whether the pilot had started for a historical window.
- Discard superseded evidence-window responses before they can update UI state.
- Keep Strategy Lab available without a latest-picks snapshot; only the
  latest-pick diagnostics subsection depends on that snapshot.

## Out of Scope

- Changes to scoring, selection, weights, pilot thresholds, or persistence.
- Recomputing or backfilling historical baskets or candidate outcomes.
- Historical single-session playback, data-quality lineage, or deployment.

## Done When

- Every displayed metric is sourced from bounded persisted evidence.
- Selecting an older window cannot include later reviews, sessions, or
  snapshots.
- Incomplete evidence remains visible and is excluded from paired comparison.
- Python tests, frontend tests/build, responsive browser QA, and documentation
  pass.

## Verification Record

- Python: 154 tests passed.
- Trace: 92.74% weighted production-line coverage (3,819/4,118 lines).
- Frontend: 16 Node tests passed; production build passed.
- Browser: live 5/10/20/all window controls, real persisted metrics, desktop and
  390px layouts, local table scrolling, page overflow, and new console errors
  checked.
- Watchdog: passed 300 seconds / 15 polls with direct and proxied endpoints,
  persisted-basket semantics, and runtime logs healthy; UI PID 724 and API PID
  21160 remain running.
