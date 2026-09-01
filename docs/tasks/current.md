# Current Task

- Maintain a minimal working BIST CLI with:
  - `import-daily-csv`
  - `refresh-investing-csvs`
  - `routine`
  - `midday-routine`
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
- Routine and midday dry-run behavior are covered by tests
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
- Reviews now load persisted history and selectable historical outcomes from SQLite and refresh after a successful routine; compact date navigation, older/newer controls, and a detail-first narrow layout keep the history usable. Other evidence panels remain typed sample data.
- Data & Runs no longer includes the UI-only Presentation states preview controls.
- The repo-local plugin exposes `refresh-data` for validated BIST CSV publication and hands successful refreshes to the direct `?view=runs` web entry point.
- The repo-local `run` launcher starts only missing UI/API components, retains component pids and ignored logs, and requires a launcher-owned five-minute post-boot watchdog result for both new and reused processes.

## Active Enhancement

- Historical Strategy Playback is implemented on
  `codex/historical-strategy-playback`.
- The read-only API loads one review-owned basket, exact signal snapshot,
  strategy metadata, stored pilot arms, and eventual outcome without invoking
  current ranking or selection logic.
- The Reviews screen preserves partial and unavailable evidence states and keeps
  its historical basket locally scrollable on narrow screens.
- The implementation scope and verification record live in
  `docs/tasks/historical-strategy-playback.md`.
- The four-item enhancement queue is recorded in `docs/tasks/backlog.md`.
- Basic GitHub CI now gates pull requests and `main` with Python tests plus
  frontend tests and a production build; deployment is intentionally deferred.
