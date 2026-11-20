---
name: routine
description: Run the full persisted Stock Expert routine, then verify SQLite persistence and git status. Use when the user says /routine, routine pls, do the routine, stock expert routine, or asks for the daily persisted BIST routine.
---

# Stock Expert Routine

Run the normal persisted routine for this repository.

## Preflight

1. Confirm the working directory is the repository root (it contains
   `stock_expert/` and `AGENTS.md`).
2. Read the repo guidance in the canonical order:
   - `memory.md`
   - `docs/tasks/current.md`
   - `docs/context/project.md`
   - `docs/rules/output.md`
3. Assume the live root CSVs in `data\` have already been refreshed. Do not ask
   whether they are current.
4. Record the current branch. If it is not `main`, say so before running:
   `routine` then writes to that branch's database, not `data/stock_expert.db`.

## Command

Run:

```powershell
python.exe -m stock_expert routine
```

## Verification

After the command finishes:

1. Verify the printed `snapshot_id`, `review_run_id`, and related
   `review_pick_results` rows in the active SQLite database. `main` uses
   `data/stock_expert.db`. Other branches use `data/stock_expert_<branch>.db`
   unless `STOCK_EXPERT_DB_PATH` overrides it.
2. Run:

```powershell
git status --short
```

## Summary

Keep the handoff short. Report the pick basket, review result, snapshot/review
ids, signal and target/review dates, SQLite verification result, and
`git status --short`.

If `routine` exits 1 with `Refusing to persist review` on stderr, report that
message and stop. Do not work around it with other commands: the review
evidence guard found a stored review that the run would contradict. See the
"Review evidence guard" section of `docs/context/trading-calendar.md`.

If stderr has a `routine: Signal window ...` line (the pick JSON's
`signal_window.status` is `gap`), report it with the basket: the signal window
skipped trading sessions, so treat the basket as degraded evidence. Scores are
unchanged.

If the routine header JSON contains `calendar_warnings`, report it first: that
year's Borsa Istanbul holiday table has not been added to
`stock_expert/trading_calendar.py`, so religious-holiday closures are being
treated as sessions. Point to the yearly update step in
`docs/context/trading-calendar.md`.

Do not expand into strategy analysis unless requested.
