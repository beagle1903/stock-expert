# Data Quality & Snapshot History

Status: implemented on `codex/data-quality-snapshot-history` on 2026-09-16.
Requirement ticket: [GitHub issue #11](https://github.com/beagle1903/stock-expert/issues/11) — still open until merge.

## Verification Record

- Python: 174 tests passed.
- Frontend: 25 Node tests passed; production build passed.
- `se-strategy-review` and `se-ui-review` approved (no Critical/Important).
- Browser: `?view=snapshots` listed 146 published rows as `not_captured`;
  snapshot #1 shows no prior; #149 compares with #148 by id. Data & Runs
  still shows Run routine. Reviews history still loads. 390px has no
  horizontal page overflow. Live DB has no captured-quality row until the
  next daily CSV import.
- Watchdog: passed 300 seconds / 15 polls; UI PID 11620, API PID 20476,
  snapshot #149; no endpoint or runtime-log failures.
- PR review follow-up: switching snapshots no longer keeps the previous
  detail visible while loading; `.reviews-view` max-width is restored.

Design: `docs/superpowers/specs/2026-09-16-data-quality-snapshot-history-design.md`.
Plan: `docs/superpowers/plans/2026-09-16-data-quality-snapshot-history.md`.

## Goal

Persist snapshot provenance and validation metrics, then expose lineage,
coverage, mapping failures, and prior-snapshot comparison in a read-only
dashboard view.

## Evidence Boundary

- Only published `snapshot_runs` rows are visible.
- Failed coverage-gate or mid-write imports create no snapshot.
- Daily CSV persist writes quality columns and mapping-failure names in the same publication transaction; `create_snapshot_run` rows stay uncaptured.
- Old rows report `provenanceStatus: not_captured`; no silent backfill.
- Comparison uses the previous published snapshot by lower `id`.
- `/api/picks/latest` remains the newest snapshot that owns picks.

## Out Of Scope

Strategy changes, backfill, failed-attempt rows, trading UI, deployment.
