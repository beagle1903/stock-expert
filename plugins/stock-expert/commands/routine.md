---
description: Run the full persisted stock expert routine and verify SQLite plus git state.
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

## Commands

Run:

```powershell
D:\miniconda3\python.exe -m stock_expert routine
```

## Verification

After the command finishes:

1. Verify the printed `snapshot_id`, `review_run_id`, and related `review_pick_results` rows in `data\stock_expert.db`.
2. Run:

```powershell
git status --short
```

## Summary

Keep the handoff short. Report:

- Pick list / basket tickers
- Review results
- Snapshot and review ids
- Signal and target/review dates
- SQLite verification result
- `git status --short` result

Always include both the new pick list and the persisted review in the final
handoff, even when there are no review wins or no downside-risk flags.

Do not expand into strategy analysis unless requested.
