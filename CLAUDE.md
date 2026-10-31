# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Stock Expert is a CLI-based BIST (Borsa Istanbul) intraday idea generator: buy-at-open / sell-at-close, ranked from end-of-day CSV snapshots (momentum, volume spikes, risk classification). It produces structured outputs, not natural-language advice. A React/Vite "Evidence Console" in `frontend/` reads the persisted SQLite evidence through a loopback-only Python API.

Read `AGENTS.md`, `memory.md`, and `docs/tasks/current.md` before starting work; `memory.md` holds decisions and gotchas that are expensive to rediscover.

## Commands

Run Python commands from the repo root. There are no third-party Python dependencies (stdlib + SQLite, Python ≥ 3.11).

```powershell
python.exe -m stock_expert routine                       # full persisted flow: import live CSVs, review prior session, persist picks
python.exe -m stock_expert review --date 2026-04-21 --dry-run   # non-mutating review check
python.exe -m stock_expert import-daily-folder --folder data\20260414   # --folder flag is required
python.exe -m stock_expert refresh-investing-csvs
python.exe -m stock_expert daily --date 2026-04-14
python.exe -m stock_expert picks --date 2026-04-14
```

Tests (unittest, no pytest):

```powershell
python.exe -m unittest discover -s tests -v              # full suite
python.exe -m unittest tests.test_services -v            # one module
python.exe -m unittest tests.test_cli.CliTests.test_routine_reviews_before_persisting_current_picks -v   # one test
```

Frontend (`frontend/`, Node 22 in CI):

```powershell
npm install
npm run dev      # starts/reuses Vite (5173) + Python API (18765) via scripts/dev.mjs
npm test         # node --test tests/*.test.mjs
npm run build
```

CI (`.github/workflows/ci.yml`) runs the Python suite and frontend test + build on PRs and `main`.

Environment: `STOCK_EXPERT_DB_PATH` (also settable in `.env`) overrides the DB; `STOCK_EXPERT_API_PORT` changes the API port (launcher and Vite proxy read it together); `STOCK_EXPERT_PYTHON` picks the Python the launcher uses.

## Architecture

- `stock_expert/cli.py` routes commands; `services.py` orchestrates `daily`, `picks`, `review`, and `routine`. `signals.py` scores; `pilot.py` runs the bucketed-default pilot arms alongside operational picks.
- Inputs are four live CSVs in `data/` (`fiyat.csv`, `performans.csv`, `teknik.csv`, `temel.csv`, git-ignored). `daily_csv.py` imports them as a `snapshot_runs` row; `investing_csv.py` validates and publishes refreshed Investing.com extracts all-or-nothing. `data/ticker_map.csv` is a name→ticker fallback.
- Dates: a data folder's name is the target trade day; its contents are stored under the previous BIST work day as the signal/snapshot date (`trading_calendar.py`). Keep signal date and trade date distinct everywhere, including the UI.
- `yahoo.py` downloads optional OHLCV backfill as `yahoo_ohlcv` snapshots; date-based operational reads ignore them so Yahoo data never enters ranking or review.
- `database.py` owns the schema. Key invariants:
  - Snapshot publication (run, market rows, prices, provenance) is one transaction.
  - `routine` persists the prior-session review **before** current picks. Review, weights, pick results, candidate outcomes, missed movers, and pilot outcomes commit as one idempotent transaction; review identity is unique on signal/review dates, and reviewed evidence is immutable on rerun.
  - Operational picks and both pilot baskets share one signal-publication transaction.
  - `--dry-run` must not write picks, signals, weights, or review rows.
- Default DB is `data/stock_expert.db` on `main`; non-`main` branches get branch-specific DBs unless `STOCK_EXPERT_DB_PATH` is set.
- `web_api.py` is a loopback-only adapter. Read endpoints (`/api/picks/latest`, `/api/reviews/*`, `/api/strategy-evidence`, `/api/strategy-playback/{id}`, `/api/snapshots/*`) never invoke ranking. The only mutating surface is Data & Runs, which shells out to `python -m stock_expert routine`.
- Frontend layering: `src/domain/*` types → `src/data/*Repository.ts` (HTTP adapters) and `*ViewModel.mjs` (pure, unit-tested by `frontend/tests`) → `src/hooks/*` → `App.tsx`. Components consume view models, never Python/SQLite concerns. `scripts/dev.mjs` + `scripts/watchdog.mjs` own process start/reuse, pid/log files in `.test_tmp/`, and a ≥5-minute post-boot health observation.
- UI direction (see `frontend/AGENTS.md`): dark Evidence Console, select-and-inspect, only show metrics backed by persisted entities; no order execution, live quotes, portfolios, forecasts, or target prices.

## Repo rules

- After each completed development change, update the relevant Markdown in `docs/features/`, `docs/context/`, `docs/tasks/`, or `memory.md` (a docs Stop hook, `.codex/hooks/validate_docs_update.py`, enforces this). Use `DOCS_NOT_NEEDED: <reason>` only when docs are deliberately unnecessary.
- Do not edit `docs/scratch/*`. Do not add `docs/superpowers/` specs/plans or `codex/` branch prefixes unless asked.
- Workflow (`docs/rules/workflow.md`): completed development work goes on a short topic branch with a PR (`gh pr create`, body with Summary + Test plan); only single obvious typo fixes go straight to `main`. GitHub issues are the requirement tickets.
- "routine" means run the full persisted `routine`, then verify SQLite persistence and `git status --short`. Assume the live CSVs are already current; don't ask.
- Operator skills live in `.cursor/skills/` (`routine`, `run`, `refresh-data`, `bist`); `plugins/bist` packages `/bist`. Codex copies under `plugins/stock-expert` are unused fallback.
