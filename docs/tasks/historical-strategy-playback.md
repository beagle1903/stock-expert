# Historical Strategy Playback Plan

Status: implemented on `codex/historical-strategy-playback` on 2026-09-01.

## Goal

Let an operator replay one preserved signal-date basket together with its exact
snapshot context, stored strategy metadata, paired pilot evidence, and eventual
review outcome without invoking current ranking or selection logic.

## Evidence Boundary

- Playback is selected by persisted `review_runs.id`.
- The operational basket comes from immutable `review_pick_results`.
- Candidate ranks and signal components join only through the selected
  `candidate_outcomes.review_run_id`.
- Market breadth and provenance use only `review_runs.signal_snapshot_id`.
- Pilot arms use only stored sessions for that exact snapshot.
- Missing legacy evidence remains explicitly unavailable; no latest-snapshot
  fallback or historical recomputation is allowed.

## Product Scope

- Add `GET /api/strategy-playback/{review_id}` as a read-only endpoint.
- Enrich the Reviews screen with signal-to-review routing, snapshot provenance,
  breadth, strategy version and weights, preserved basket attribution, realized
  outcomes, and stored pilot arms.
- Preserve partial and unavailable states for missing snapshot, candidate, and
  pilot evidence.
- Keep wide basket data inside a local horizontal scroller on narrow screens.

## Out Of Scope

- Strategy, scoring, selection, weights, persistence, or schema changes.
- Backfilling legacy reviews or candidate outcomes.
- Reconstructing an old exposure policy with current rules.
- Alerts, execution, forecasts, or personalized advice.

## Verification Record

- Python: 156 tests passed.
- Trace: 93.06% weighted production-line coverage (3,941/4,235 lines).
- Frontend: 18 Node tests passed; production build passed.
- Real SQLite: 85 reviews loaded; latest exact snapshot, five-pick basket,
  partial attribution, and both pilot arms verified.
- Browser: latest and legacy playback, date switching, desktop and 390px
  layouts, local table scrolling, page overflow, and console errors checked.
- Watchdog: passed 300 seconds / 15 polls with UI PID 7720 and API PID 7240.

## Done When

- A selected review cannot read a later snapshot or another review's candidate
  evidence.
- Preserved basket and outcome rows remain useful when optional evidence is
  absent.
- Desktop/mobile browser QA, full tests/build, coverage, watchdog, and project
  documentation pass.
