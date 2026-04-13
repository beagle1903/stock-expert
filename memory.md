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

## Workflows

Document repeatable ways of doing things in this repo.

### Common Commands

- `D:\miniconda3\python.exe -m stock_expert import-daily-csv --date 2026-04-05`
- `D:\miniconda3\python.exe -m stock_expert import-daily-folder --folder data\YYYYMMDD`
- `D:\miniconda3\python.exe -m stock_expert daily --date YYYY-MM-DD`
- `D:\miniconda3\python.exe -m stock_expert picks --date YYYY-MM-DD`
- `D:\miniconda3\python.exe -m stock_expert review --date YYYY-MM-DD`

### Daily CSV Routine

1. Check the newest dated folder under `data\`.
2. Confirm it contains `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv`.
3. Import with `D:\miniconda3\python.exe -m stock_expert import-daily-folder --folder data\YYYYMMDD`.
4. Run `daily`, `picks`, and `review` with the imported snapshot date.

### Data Inputs

- Daily CSV inputs: `fiyat.csv`, `performans.csv`, `teknik.csv`, `temel.csv`

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

## Data Sources And External Dependencies

- SQLite database: `data/stock_expert.db`
- CSV source files: `fiyat.csv`, `performans.csv`, `teknik.csv`, `temel.csv`

## Open Questions

- Should old absolute-path links in docs be updated to the new workspace path?
- What project-specific lessons should be promoted here from future task work?

## Change Log For This File

Use this only for meaningful memory-management changes, not every repo change.

| Date | Update |
| --- | --- |
| 2026-04-09 | Created initial durable-memory file and seeded it with repo-specific context. |
