---
name: routine
description: Run the full persisted stock expert routine workflow, then verify SQLite persistence and git status. Use when the user says /routine, routine pls, do the routine, stock expert routine, or asks for the daily persisted BIST routine.
metadata:
  priority: 8
  pathPatterns:
    - "memory.md"
    - "stock_expert/cli.py"
    - "docs/tasks/current.md"
  bashPatterns:
    - "stock_expert routine"
    - "python.exe -m stock_expert routine"
---

# Stock Expert Routine

Run the normal persisted routine for this repository.

## Preflight

1. Confirm the working directory is `C:\Users\burha\Documents\dev\stock expert`.
2. Read the repo guidance in the canonical order:
   - `memory.md`
   - `docs/tasks/current.md`
   - `docs/context/project.md`
   - `docs/rules/output.md`
3. Assume the live root CSVs in `data\` have already been refreshed. Do not ask whether they are current.

## Command

Run:

```powershell
D:\miniconda3\python.exe -m stock_expert routine
```

## Verification

After the command finishes:

1. Verify the printed `snapshot_id`, `review_run_id`, and related `review_pick_results` rows in the active SQLite database.
2. Run:

```powershell
git status --short
```

## Summary

Keep the handoff short. Report the pick basket, review result, snapshot/review ids, signal and target/review dates, SQLite verification result, and `git status --short`.

Do not expand into strategy analysis unless requested.
