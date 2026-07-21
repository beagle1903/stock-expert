# Feature: Dashboard Prototype

- `frontend/` contains the approved dark Evidence Console prototype.
- The default screen is a select-and-inspect view for persisted picks, pick evidence, exposure policy, latest review, and routine status.
- Signal date and target trade date are always labeled separately.
- The Reviews screen reads the newest `review_runs` row and its `review_pick_results` from SQLite through the loopback API.
- `src/data/dashboardRepository.ts` overlays that persisted review onto the typed sample data still used by picks, diagnostics, exposure, snapshot, and timeline panels.
- Data & Runs uses `stock_expert.web_api` to preview and execute the real persisted CLI routine through a loopback-only API.
- The launcher resolves weekends/confirmed holidays through the shared trading calendar, shows signal date separately from target trade date, and surfaces market-context policy.
- Missing, empty, or filesystem-stale CSV inputs block execution. Newer timestamps warn because file metadata cannot prove the market date inside the rows.
- Execution requires a current preview token, a second confirmation step, and an explicit operator checkbox. Only one routine can run at a time.
- Successful runs report the persisted snapshot id, pick count, and review id when a prior basket is eligible for review.
- After a successful run, the dashboard repository reloads so the Reviews screen immediately displays the latest persisted review id and outcomes.
- Navigation covers overview, today's picks, reviews, diagnostics, and data/runs without adding execution, portfolio, live-quote, or forecast capabilities.
- Dashboard loading and retry states remain available; Data & Runs shows only real routine readiness, confirmation, running, success, and failure states rather than UI-only presentation previews.
- Desktop, tablet, and mobile layouts preserve keyboard focus and explicit date/freshness labels.

## Commands

```powershell
cd frontend
npm install
npm run dev
npm run build
```

`npm run dev` starts both Vite and the local routine API. Set `STOCK_EXPERT_PYTHON` when the desired Python executable is not on `PATH`; Windows development also recognizes `D:\miniconda3\python.exe`.

The repo-local Codex command `/stock-expert:run` starts or reuses that same
development pair, verifies the UI on `http://127.0.0.1:5173/` and API health on
port `8765`, then opens the UI in Codex's built-in browser. Bare `/run` is the
workspace shorthand.
