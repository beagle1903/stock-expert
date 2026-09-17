# Current Task

- Maintain a minimal working BIST CLI with:
  - `import-daily-csv`
  - `refresh-investing-csvs`
  - `routine`
  - `daily`
  - `picks`
  - `review`

## Constraints

- Keep outputs concise and structured
- Prefer simple solutions
- Avoid unrelated refactors
- Ask before adding dependencies or major architecture changes

## Done When

- Commands run end-to-end
- Review explains missed movers clearly
- Daily CSV import flow is available
- Live root CSV routine supports repeated same-day imports
- Rendered Investing.com tables can refresh all four live CSVs with cross-table coverage validation and rollback-safe publication
- Routine and `review --dry-run` behavior are covered by tests
- Snapshot and review persistence are atomic and idempotent
- Historical review evidence is point-in-time and immutable
- Standard-library trace coverage remains at or above 90% across production modules

## Bucketed-Default Pilot

- [x] Persist complete breadth-matched score-ranked and bucketed baskets
- [x] Use bucketed as the active default without changing candidate scoring
- [x] Freeze momentum/volume weights while the pilot is active
- [x] Count only complete paired review sessions
- [x] Roll back at a -3 percentage-point compounded edge
- [x] Decide promotion after 10 sessions using at least 6 wins and a +3-point edge
- [x] Apply terminal review decisions before persisting the next basket
- [x] Publish operational and paired pilot baskets atomically
- [x] Keep pre-start dates outside pilot evidence and evaluate sessions chronologically
- [x] Make reviewed baskets immutable and persist missing-price sessions as incomplete

## Frontend Prototype

- Dark Evidence Console implemented under `frontend/` with typed mock data and an explicit future repository boundary.
- Responsive browser and design QA are recorded in `frontend/design-qa.md`.
- Live evidence-panel API integration remains deferred; Python strategy and SQLite behavior are unchanged.
- Data & Runs now has a loopback-only persisted routine launcher with holiday/missed-day routing, CSV readiness checks, confirmation, progress, and result IDs.
- The repo-local `/stock-expert:run` command starts or reuses the web app and opens it in Codex's built-in browser.
- Cursor overlay skills in `.cursor/skills/` are the current operator path for `routine`, `run`, and `refresh-data`; the Codex plugin remains unused fallback. See `docs/context/cursor-operator.md`.
- Reviews now load persisted history and selectable historical outcomes from SQLite and refresh after a successful routine; compact date navigation, older/newer controls, and a detail-first narrow layout keep the history usable. Other evidence panels remain typed sample data.
- Data & Runs no longer includes the UI-only Presentation states preview controls.
- The repo-local plugin exposes `refresh-data` for validated BIST CSV publication and hands successful refreshes to the direct `?view=runs` web entry point.
- The repo-local `run` launcher starts only missing UI/API components, retains component pids and ignored logs, and requires a launcher-owned five-minute post-boot watchdog result for both new and reused processes.

## Active Enhancement

- Fade-then-rechase penalty and miss tags shipped on `main` via
  [PR #23](https://github.com/beagle1903/stock-expert/pull/23). GitHub issue
  #21 is closed. See `docs/tasks/fade-then-rechase.md`.
- Snapshots API (`/api/snapshots/history`, `/api/snapshots/{id}`) and the
  read-only Evidence Console Snapshots view shipped on `main` via
  [PR #19](https://github.com/beagle1903/stock-expert/pull/19). GitHub issue
  #11 is closed. Verification is in
  `docs/tasks/data-quality-snapshot-history.md`.
- Spec: `docs/superpowers/specs/2026-09-16-data-quality-snapshot-history-design.md`.
- Plan: `docs/superpowers/plans/2026-09-16-data-quality-snapshot-history.md`.
- Implementation notes: `docs/tasks/data-quality-snapshot-history.md`.
- Basic GitHub CI now gates pull requests and `main` with Python tests plus
  frontend tests and a production build; deployment is intentionally deferred.
- Optional Yahoo path and `midday-routine` removal shipped on `main` via
  [PR #25](https://github.com/beagle1903/stock-expert/pull/25). GitHub issue
  #14 is closed. See `docs/features/download-ohlcv.md`.
- Removed redundant `openwiki/` generated wiki; `docs/` is the source of truth.
