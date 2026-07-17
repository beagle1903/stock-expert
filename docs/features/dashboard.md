# Feature: Dashboard Prototype

- `frontend/` contains the approved dark Evidence Console prototype.
- The default screen is a select-and-inspect view for persisted picks, pick evidence, exposure policy, latest review, and routine status.
- Signal date and target trade date are always labeled separately.
- Visible values are typed mock data shaped around current `picks`, `signals`, `market_snapshots`, `review_runs`, `review_pick_results`, `candidate_outcomes`, and `snapshot_runs` concepts.
- `src/data/dashboardRepository.ts` is the presentation/data-access seam; it currently returns local mock data and does not call Python or SQLite.
- Navigation covers overview, today's picks, reviews, diagnostics, and data/runs without adding execution, portfolio, live-quote, or forecast capabilities.
- Loading, empty, and stale-data error states are available from the Data & Runs screen.
- Desktop, tablet, and mobile layouts preserve keyboard focus and explicit date/freshness labels.

## Commands

```powershell
cd frontend
npm install
npm run dev
npm run build
```
