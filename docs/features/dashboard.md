# Feature: Dashboard

- `frontend/` contains the approved dark Evidence Console.
- The default screen is a select-and-inspect view for persisted picks, pick evidence, exposure policy, latest review, and routine status.
- Signal date and target trade date are always labeled separately.
- The Reviews screen reads the newest `review_runs` row and its `review_pick_results` from SQLite through the loopback API, lists all persisted review summaries through `/api/reviews/history`, and loads selected historical outcomes through `/api/reviews/{id}`. A compact date navigator, older/newer controls, bounded history list, and detail-first narrow layout keep historical outcomes immediately reachable.
- Selected review detail includes a filterable Missed-Mover Explorer backed only by captured `review_missed_mover_results`. It shows stored actionability, reason, realized return, candidate rank, selection note, and signal adjustments; legacy reviews render a not-captured explanation instead of recomputation.
- Today's Picks reads the newest signal-date snapshot that owns a persisted `picks` basket through `/api/picks/latest`; later price-only repair snapshots cannot hide the operational basket. Signal and target-trade dates, snapshot metadata, exposure, diagnostics, and run timeline come from that persisted snapshot rather than sample data.
- Strategy Lab reads `/api/strategy-evidence` with selectable 5, 10, 20, or all-review windows. It shows pilot status and thresholds, complete paired score-ranked versus bucketed results, cutoff and rank-band diagnostics, setup-penalty comparison, exact-snapshot breadth, and persisted session integrity.
- Strategy Lab labels missing candidate outcomes, unavailable signal snapshots, and incomplete or unpaired pilot sessions. Only complete paired sessions contribute to the strategy comparison.
- Historical pilot status uses the final selected signal date for the pilot-start boundary, while review dates continue to bound persisted outcomes; pre-pilot baskets cannot be mislabeled active merely because they were reviewed after the start date.
- Strategy Lab remains reachable when no latest-picks snapshot exists, renders its persisted review evidence independently, and limits the empty state to the latest-pick subsection.
- Evidence-window loads use latest-request-wins semantics so a superseded response cannot overwrite the currently selected window.
- The dashboard repository loads the latest picks, latest review, and review-history endpoints together and reloads them after a successful routine; historical detail selection remains read-only.
- Data & Runs uses `stock_expert.web_api` to preview and execute the real persisted CLI routine through a loopback-only API.
- The launcher resolves weekends/confirmed holidays through the shared trading calendar, shows signal date separately from target trade date, and surfaces market-context policy.
- Missing, empty, or filesystem-stale CSV inputs block execution. Newer timestamps warn because file metadata cannot prove the market date inside the rows.
- Execution requires a current preview token, a second confirmation step, and an explicit operator checkbox. Only one routine can run at a time.
- Successful runs report the persisted snapshot id, pick count, and review id when a prior basket is eligible for review.
- After a successful run, the dashboard repository reloads so both Today’s Picks and Reviews immediately display the newest persisted results.
- Navigation covers overview, today's picks, reviews, diagnostics, and data/runs without adding execution, portfolio, live-quote, or forecast capabilities.
- `?view=runs` opens Data & Runs directly so a completed data-refresh command can hand off to routine confirmation without a second navigation step.
- Dashboard loading and retry states remain available; Data & Runs shows only real routine readiness, confirmation, running, success, and failure states rather than UI-only presentation previews.
- An unexpectedly empty persisted basket renders an explicit empty state on pick-dependent views instead of collapsing the workspace to its header.
- Desktop, tablet, and mobile layouts preserve keyboard focus and explicit date/freshness labels.
- Strategy Lab keeps wide evidence tables inside local horizontal scrollers and bounds long breadth histories so the page itself does not overflow at narrow widths.
- The desktop right column sizes Exposure policy to its content and gives the remaining height to the scrollable review, preventing the two panels from overlapping above the run timeline.

## Commands

```powershell
cd frontend
npm install
npm run dev
npm run build
```

`npm run dev` starts both Vite and the local routine API. The API defaults to
loopback port `18765`; set `STOCK_EXPERT_API_PORT` to use another available
port. The launcher and Vite proxy resolve this setting together. Set
`STOCK_EXPERT_PYTHON` when the desired Python executable is not on `PATH`;
Windows development also recognizes `D:\miniconda3\python.exe`.

The repo-local Codex command `/stock-expert:run` starts or reuses that same
development pair, verifies the UI on `http://127.0.0.1:5173/` and API health on
port `18765` by default, then opens the UI in Codex's built-in browser. Bare
`/run` is the workspace shorthand.

The launcher owns a post-ready observation window of at least five minutes for
both started and reused processes. It records separate UI/API logs and pids in
ignored `.test_tmp/`, polls liveness plus direct/proxied dashboard endpoints,
rejects empty/duplicate/repair-snapshot baskets and port drift, scans newly
logged runtime errors, and persists a pass/fail operator summary with likely
cause and log tails. Production uses a 20-second interval; automated tests must
explicitly opt into shortened timing.
