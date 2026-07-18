# Current Task

- Maintain a minimal working BIST CLI with:
  - `import-daily-csv`
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
- Routine and midday dry-run behavior are covered by tests
- Snapshot and review persistence are atomic and idempotent
- Historical review evidence is point-in-time and immutable
- Standard-library trace coverage remains at or above 90% across production modules

## Frontend Prototype

- Dark Evidence Console implemented under `frontend/` with typed mock data and an explicit future repository boundary.
- Responsive browser and design QA are recorded in `frontend/design-qa.md`.
- Live evidence-panel API integration remains deferred; Python strategy and SQLite behavior are unchanged.
- Data & Runs now has a loopback-only persisted routine launcher with holiday/missed-day routing, CSV readiness checks, confirmation, progress, and result IDs.
- Evidence panels remain typed sample data and are labeled accordingly; loading live dashboard entities is still deferred.
