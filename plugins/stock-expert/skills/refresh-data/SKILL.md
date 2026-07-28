---
name: refresh-data
description: Refresh and validate Stock Expert's four live Investing.com BIST CSV inputs, then hand off to the guarded Data & Runs web UI. Use when the user says refresh data, fetch recent BIST data, update the Investing.com CSVs, prepare data for the routine, or asks for refresh-investing-csvs.
---

# Refresh BIST Data

Refresh the live CSV bundle without importing it or running the routine.

## Preflight

1. Confirm the working directory is `C:\Users\burha\Documents\dev\stock expert`.
2. Read `memory.md`, `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
3. Preserve unrelated worktree changes and record `git status --short`.

## Refresh

Run from the repository root:

```powershell
D:\miniconda3\python.exe -m stock_expert refresh-investing-csvs
```

The command uses a visible browser, selects all Türkiye shares, expands the
rendered table by page state, validates all four tabs, and publishes the bundle
atomically. Do not bypass CAPTCHA, Cloudflare, or another access challenge.
When a challenge appears, ask the user to complete it in the visible browser.

Do not run `routine` automatically. Data refresh and persisted execution are
separate operator actions.

## Verify

Require all of the following before reporting success:

- `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv` each meet the
  minimum row count reported by the command.
- The command confirms matching company coverage and expected schemas.
- Each published file is non-empty and starts with the UTF-8 BOM.
- `git status --short` is recorded after publication.

## Web Handoff

Unless the user requested CLI-only output, read `../run/SKILL.md`, follow its
start-or-reuse procedure, and open:

```text
http://127.0.0.1:5173/?view=runs
```

Leave the persisted routine for the user to review and confirm in Data & Runs.
Report the four row counts, publication result, UI/API health, and git status.
