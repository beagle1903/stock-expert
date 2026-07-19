# Project Memory

This file is the durable working memory for this repository.

Use it to capture information that is expensive to rediscover and likely to matter again. Keep it concise, concrete, and easy to trust.

## How To Use This File

- Record durable decisions, not scratch notes.
- Prefer facts, constraints, and proven workflows over speculation.
- Update this file when we learn something that will help future work move faster or avoid repeated mistakes.
- Rewrite or prune stale sections instead of letting them accumulate noise.
- Do not use this file as a substitute for code comments, tests, or proper user-facing documentation.

## Project Snapshot

- Purpose: Python CLI for BIST intraday idea generation and review.
- Runtime mode: Daily CSV snapshots.
- Main stack: Python 3.11+, setuptools, SQLite.
- CLI entry point: `stocks` -> `stock_expert.cli:main`
- Key package: `stock_expert/`
- Main data store: `data/stock_expert.db`

## Canonical Read Order

When starting work, read these first:

1. `docs/tasks/current.md`
2. `docs/context/project.md`
3. `docs/rules/output.md`

Then consult as needed:

- `docs/context/architecture.md`
- `docs/context/decisions.md`
- `docs/features/*`
- `docs/tasks/backlog.md`

## Decisions

Use this section for architecture or workflow decisions that affect future changes.

| Date | Decision | Why It Matters |
| --- | --- | --- |
| 2026-04-09 | Added `memory.md` as a durable repo memory file for human and agent collaboration. | Preserves hard-won context across sessions without relying on chat history. |
| 2026-04-10 | Non-`main` git branches now default to branch-specific SQLite files like `data/stock_expert_codex_add_indicators.db`; `main` keeps `data/stock_expert.db`. | Prevents branch experiments from contaminating the primary database and makes branch-to-branch comparisons safer. |
| 2026-04-20 | Live root CSVs are the default input; imports create timestamped SQLite snapshot runs instead of relying on dated archive folders. | Supports running the routine more than once during the same BIST session without overwriting earlier action snapshots. |
| 2026-04-20 | Daily CSV import skips obvious non-equity portfolio-management/fund rows unless explicitly allowlisted. | Prevents fund/portfolio entities from becoming synthetic stock picks while allowing trusted aliases such as `HEDEFPORTFOYYONETIMIAS -> HEDEF`. |
| 2026-04-21 | `routine` is the full end-to-end flow with actual persisted review; `midday-routine` is the import + daily + picks + dry-run review flow. | Keeps the midday dry-run review flow separate from the full review command path and matches the intended operator language. |
| 2026-04-21 | Repo test coverage now uses `unittest` in `tests/` for routine wiring, weekday date helpers, and dry-run review persistence boundaries. | Adds regression protection without introducing a new test dependency. |
| 2026-04-21 | Picks now keep momentum/volume as the base score but add capped technical, quality, and fundamental soft boosts from imported snapshot data. | Brings `teknik.csv` and `temel.csv` into live ranking without replacing the core anti-chase momentum workflow. |
| 2026-04-21 | GitHub remote backup is now active at `https://github.com/beagle1903/stock-expert`, with `main` as the default/stable branch. | Makes the repo recoverable off-laptop and establishes `main` as the source of truth after feature branches are merged. |
| 2026-04-22 | `routine` includes persisted picks and persisted review after the live CSV import. | Keeps the main operator workflow focused on the actual recorded strategy result. |
| 2026-04-23 | Daily CSV imports now skip unmapped company names, report malformed required rows, and label derived CSV prices as previous-close-to-latest rather than true open-to-close. | Prevents fabricated tickers and makes review/daily outputs honest about the available feed semantics. |
| 2026-04-23 | Persisted `review` is idempotent per signal/review date and weight changes now depend on return, win rate, and actionable misses. | Avoids repeated review drift while keeping the feedback loop tied to observed outcomes. |
| 2026-04-23 | Non-trivial work should use feature-scoped branches named `codex/<task-name>`, then merge to `main` only after behavior is trusted. | Features often span model, schema, docs, tests, and deployment notes, so branch by feature instead of technical layer. |
| 2026-04-30 | Trading-date helpers skip the user-confirmed full-day market holiday `2026-05-01`. | Keeps April 30 picks and May 4 review aligned across the Friday holiday. |
| 2026-05-04 | Picks now subtract a capped `setup_penalty` for weak or stretched snapshot context before ranking. | Penalizes bearish technical alignment, missing/weak fundamentals, abnormal volume context, and crowded weekly/monthly momentum without replacing the base momentum/volume model. |
| 2026-05-05 | Review win classification now requires at least 4% daily return. | Raises the strategy standard so small positive returns count as losses in win rate, persisted wins, and pick-level `won` rows. |
| 2026-05-13 | Bucketed final selection was added as an experimental comparison path. | It composes 2 core momentum, 2 breakout technical, and 1 coverage recovery pick, while preserving `selection_bucket` for review diagnostics. |
| 2026-05-15 | Default persisted picks returned to score-ranked top 5; bucketed selection is dry-run/reporting only. | Recent DB-backed checks showed score-ranked top 5 outperforming bucketed selection, so `routine` reports score-ranked vs bucketed review comparison. |
| 2026-06-23 | Score-ranked persisted picks now adapt down to top 3 when point-in-time rolling candidate evidence favors `top_3` and top-5 average return is negative. | Keeps the default strategy conservative after repeated near-term evidence that the full top-5 cutoff is underperforming, without flipping to bucketed selection yet. |
| 2026-05-15 | Removed no-chase comparison from the operator workflow and added downside-risk diagnostics for actual picks. | Equal-weight investing only cares about set membership, and the no-chase basket often matched the normal basket; downside flags catch falling intraday names such as large same-day drops with bearish hourly technicals. |
| 2026-05-21 | Marked 2026-05-21, 2026-05-22, and 2026-05-25 as political-shock context and enabled shock-mode persisted selection on tagged signal dates. | The May 21 BIST selloff was treated as exogenous political risk; tagged signal dates add capped downside penalties for bearish hourly/daily/weekly context and large same-day drops. |
| 2026-05-26 | Marked 2026-05-26 as a half-holiday/low-liquidity context and 2026-05-27 through 2026-05-29 as exact exchange-closed dates; 2026-06-01 remains open. | Keeps holiday-week picks targeted at June 1 while avoiding recurring religious-holiday rules, because those holidays shift each year. |
| 2026-07-15 | Added July 15 as a recurring annual BIST closure. | Routes the live July 15 holiday snapshot to the prior trading signal date and the next open session. |
| 2026-06-03 | Added breadth-based exposure caps, persisted top-candidate outcomes, rolling candidate diagnostics, and rolling review-weight updates. | Avoids forcing five picks into weak markets and creates evidence for near-cutoff misses and score-ranked versus bucketed selection before changing the default strategy. |
| 2026-06-03 | Added a project-local Codex Stop hook that requires relevant Markdown updates after development work. | Keeps feature, context, task, or durable memory documentation aligned with code changes; deliberate exceptions require a `DOCS_NOT_NEEDED` reason. |
| 2026-06-04 | Rolling candidate diagnostics now include cumulative top 3/5/10/20/50 cutoff analysis and a best observed cutoff. | Turns persisted candidate outcomes into direct evidence for whether the pick-count cutoff should stay tight or expand before changing selection defaults. |
| 2026-06-14 | Snapshot publication and persisted reviews now use atomic transactions; historical review inputs are date-bounded and candidate evidence is immutable on rerun. | Prevents partial latest snapshots, future-state leakage, duplicate reviews, and rewritten strategy evidence. |
| 2026-06-14 | Trading-session routing moved to one shared calendar, routine rankings are request-cached, and unknown git state uses an isolated database. | Keeps holiday alignment consistent, reduces repeated ranking work, and protects the main database outside an explicit `main` branch. |
| 2026-06-14 | Production line coverage is measured with the standard-library `trace` module because `coverage.py` is not installed; focused Yahoo, signal, CLI, config, and database tests raised weighted coverage to about 94%. | Keeps coverage verification dependency-free while protecting secondary ingestion and direct command routes. |
| 2026-06-22 | Added a repo-scoped Codex plugin marketplace with `/stock-expert:routine`. | Gives the routine workflow a project-local slash command without relying on deprecated global custom prompts. |
| 2026-07-08 | The repo-scoped Codex plugin uses `skills/routine/SKILL.md` as its canonical routine registration. | Codex composer autocomplete indexes skills in this build; keeping the legacy `commands/` copy would create duplicate autocomplete entries through automatic command migration. |
| 2026-07-17 | The approved frontend direction is a dark Evidence Console implemented under `frontend/` with typed mock data behind a repository interface. | Keeps the first web slice faithful to persisted CLI entities while isolating presentation from future API access and avoiding invented trading capabilities. |
| 2026-07-18 | Data & Runs executes the existing persisted routine through a loopback-only standard-library API with shared-calendar preview, CSV readiness checks, a current confirmation token, and a single-run lock. | Adds a guarded web operator path without duplicating or changing CLI strategy and SQLite semantics; evidence panels remain explicitly labeled sample data until their API adapter is implemented. |
| 2026-07-18 | Added `/stock-expert:run` to start or reuse the loopback web app and open it in Codex's built-in browser. | Keeps web startup on the existing `frontend/scripts/dev.mjs` path, avoids duplicate servers, and makes the UI directly accessible from the project-local plugin. |

## Workflows

Document repeatable ways of doing things in this repo.

### Common Commands

- `git checkout -b codex/<topic>`
- `git checkout main`
- `git merge <feature-branch>`
- `git push -u origin main`
- `D:\miniconda3\python.exe -m stock_expert routine`
- `D:\miniconda3\python.exe -m stock_expert midday-routine`
- `D:\miniconda3\python.exe -m stock_expert import-daily-csv --date 2026-04-05`
- `D:\miniconda3\python.exe -m stock_expert import-daily-folder --folder data\YYYYMMDD`
- `D:\miniconda3\python.exe -m stock_expert daily --date YYYY-MM-DD`
- `D:\miniconda3\python.exe -m stock_expert picks --date YYYY-MM-DD`
- `D:\miniconda3\python.exe -m stock_expert review --date YYYY-MM-DD`
- `D:\miniconda3\python.exe -m unittest discover -s tests -v`

### Daily CSV Routine

When the user says "do the routine", use the four live root CSVs in `data\`, import a new snapshot run, then run `daily`, normal `picks`, the actual persisted `review`, score-ranked vs bucketed review comparison, and downside-risk diagnostics for the actual picks.

When the user says "do the midday routine", use the same live CSV import flow, then run `daily`, normal `picks`, and `review --dry-run`.

When the user requests any type of routine, assume the live root CSVs have already been refreshed up to the minute; do not ask whether the CSVs are current before running the requested routine.

After each actual `routine`, offer a DB-backed miss analysis and one or two concrete repo improvements based on the persisted review, recent misses, and active thresholds.

Live files:

- `data\fiyat.csv`
- `data\performans.csv`
- `data\teknik.csv`
- `data\temel.csv`

1. Replace the four live CSV files with current exports.
2. Run `D:\miniconda3\python.exe -m stock_expert routine` for the full flow or `D:\miniconda3\python.exe -m stock_expert midday-routine` for the midday dry-run review flow.
3. The routine imports a new `snapshot_runs` row for today's date and uses the latest snapshot for output.
4. `routine` persists normal picks and the normal review, then prints non-mutating score-ranked vs bucketed comparison and downside-risk diagnostics; `midday-routine` keeps review non-mutating via `--dry-run`.
5. Use `midday-routine` when the user wants the midday dry-run review behavior from yesterday.
6. Run CLI commands from the repo root unless the package is installed in the active environment.

### Strategy Comparison

- Use `--dry-run` for comparison runs; it must not write picks, signals, weights, or review rows.
- Use `midday-routine` for midday dry-run review checks without mutating review state.
- Use `routine` for the actual persisted review flow plus reporting-only diagnostics.

### Testing

- Run `D:\miniconda3\python.exe -m unittest discover -s tests -v` from the repo root.
- Current tests cover `routine` vs `midday-routine` CLI wiring, weekday date helpers, review dry-run persistence boundaries, CSV import of `Gelir`/`F/K`, bounded technical/fundamental/setup-penalty scoring behavior, score-ranked default picks, and bucketed comparison reporting.
- Review diagnostics depend on persisted `candidate_outcomes`; the first persisted review after this feature seeds the rolling evidence window.

### Git Workflow

- `main` is the stable branch and should match `origin/main`.
- Use feature-scoped branches named `codex/<task-name>` for non-trivial work, especially anything strategy-affecting, persistence-affecting, or deployment-related.
- Keep all related feature changes on the same branch, even when they span model logic, schema, CLI output, tests, docs, memory, and deployment notes.
- Merge a feature branch back into `main` only after behavior is trusted through tests and any relevant dry-run routine checks.
- Tiny typo/docs fixes may still go directly to `main` when the scope is obvious.
- Push `main` after merges so GitHub remains the backup/source of truth.
- The old long-running `codex/add-indicators` branch has been merged and removed.

### Data Inputs

- Daily CSV inputs: `fiyat.csv`, `performans.csv`, `teknik.csv`, `temel.csv`
- Root live CSV inputs are ignored by git; durable import history lives in SQLite `snapshot_runs`.

## Repo Conventions

- Keep responses under 300 words.
- Do not modify `docs/scratch/*` during normal task work.
- Follow the existing docs and folder structure.
- Root guidance lives in `AGENTS.md`.
- Feature docs live in `docs/features/`.
- Review and trust project-local Codex hooks through `/hooks`; hook trust must be renewed after hook definition changes.
- The local Codex plugin is sourced from `.agents/plugins/marketplace.json` and `plugins/stock-expert`; reinstall it with `codex plugin add stock-expert@stock-expert-local` after changing plugin metadata.

## Gotchas

- This workspace root is `C:\Users\burha\Documents\dev\stock expert`.
- The old path `C:\Users\burha\Documents\stock expert` is obsolete and should not be used for ongoing work.
- Some links in root docs may still point at the old absolute path and should be treated carefully if referenced directly.
- `STOCK_EXPERT_DB_PATH` overrides the default SQLite path when a task needs an explicit database target.
- `python` may not be on PATH in this workspace shell; use `D:\miniconda3\python.exe` for CLI runs.
- `import-daily-folder` requires the `--folder` flag; a positional folder path is rejected.
- Dated data folders can be ahead of the current calendar date, so verify the folder name and import snapshot date explicitly.
- Daily data folder names represent the target weekday/work day for the picks; `import-daily-folder` stores the CSV contents under the previous weekday/work day `snapshot_date`/signal date and returns both dates.
- Dated archive folders under `data\YYYYMMDD` were legacy inputs; the default flow now uses root live CSVs and SQLite snapshot history.
- Current reads use the latest snapshot for each date, so multiple same-day imports can coexist while existing date-based commands keep working.
- A local `.env` can pin `STOCK_EXPERT_DB_PATH` and takes effect before branch-based default DB selection.
- `review --date YYYY-MM-DD` evaluates realized market data for that date against picks generated from the previous weekday signal date.
- `--dry-run` is the safe path for old-strategy comparisons because normal `picks`/`review` mutate SQLite state.
- Review candidate recomputation must stay dry-run even during a persisted review; otherwise strategy changes can rewrite the historical pick basket before it is evaluated.
- Variable-date religious/exchange holidays must be recorded as exact confirmed dates; stable annual closures such as July 15 may use recurring month/day rules.
- Workspace-local temp directories are safer than OS temp directories for tests in this environment.
- `.test_tmp/` is a local test artifact folder and should stay ignored.

## Data Sources And External Dependencies

- SQLite database: `data/stock_expert.db`
- CSV source files: `fiyat.csv`, `performans.csv`, `teknik.csv`, `temel.csv`
- GitHub remote: `https://github.com/beagle1903/stock-expert`

## Open Questions

- Should old absolute-path links in docs be updated to the new workspace path?
- What project-specific lessons should be promoted here from future task work?

## Change Log For This File

Use this only for meaningful memory-management changes, not every repo change.

| Date | Update |
| --- | --- |
| 2026-04-09 | Created initial durable-memory file and seeded it with repo-specific context. |
