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
| 2026-04-22 | `routine` now includes the persisted flow plus a no-chase-penalty dry-run picks/review comparison after the normal review. | Bakes the main strategy comparison into the default operator workflow without mutating SQLite twice. |
| 2026-04-23 | Daily CSV imports now skip unmapped company names, report malformed required rows, and label derived CSV prices as previous-close-to-latest rather than true open-to-close. | Prevents fabricated tickers and makes review/daily outputs honest about the available feed semantics. |
| 2026-04-23 | Persisted `review` is idempotent per signal/review date and weight changes now depend on return, win rate, and actionable misses. | Avoids repeated review drift while keeping the feedback loop tied to observed outcomes. |

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
- `D:\miniconda3\python.exe -m stock_expert picks --date YYYY-MM-DD --dry-run --no-chase-penalty`
- `D:\miniconda3\python.exe -m stock_expert review --date YYYY-MM-DD --dry-run --no-chase-penalty`
- `D:\miniconda3\python.exe -m unittest discover -s tests -v`

### Daily CSV Routine

When the user says "do the routine", use the four live root CSVs in `data\`, import a new snapshot run, then run `daily`, normal `picks`, the actual persisted `review`, and a no-chase-penalty dry-run `picks` + `review` comparison.

When the user says "do the midday routine", use the same live CSV import flow, then run `daily`, normal `picks`, and `review --dry-run`.

Live files:

- `data\fiyat.csv`
- `data\performans.csv`
- `data\teknik.csv`
- `data\temel.csv`

1. Replace the four live CSV files with current exports.
2. Run `D:\miniconda3\python.exe -m stock_expert routine` for the full flow or `D:\miniconda3\python.exe -m stock_expert midday-routine` for the midday dry-run review flow.
3. The routine imports a new `snapshot_runs` row for today's date and uses the latest snapshot for output.
4. `routine` persists normal picks and the normal review, then prints a non-mutating no-chase-penalty dry-run picks/review comparison; `midday-routine` keeps review non-mutating via `--dry-run`.
5. Use `midday-routine` when the user wants the midday dry-run review behavior from yesterday.
6. Run CLI commands from the repo root unless the package is installed in the active environment.

### Strategy Comparison

- Use `--dry-run` for comparison runs; it must not write picks, signals, weights, or review rows.
- Use `--no-chase-penalty` to compare against the overextended-mover penalty strategy.
- Current comparison candidate for 2026-04-17 without chase penalty: `MERCN`, `CRFSA`, `KONTR`, `PRZMA`, `FONET`.
- Use `midday-routine` for midday dry-run review checks without mutating review state.
- Use `routine` for the actual persisted review flow plus the no-chase dry-run comparison.

### Testing

- Run `D:\miniconda3\python.exe -m unittest discover -s tests -v` from the repo root.
- Current tests cover `routine` vs `midday-routine` CLI wiring, weekday date helpers, review dry-run persistence boundaries, CSV import of `Gelir`/`F/K`, and bounded technical/fundamental scoring behavior.

### Git Workflow

- `main` is the stable branch and should match `origin/main`.
- Use short-lived feature branches for larger changes, then merge back into `main`.
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
