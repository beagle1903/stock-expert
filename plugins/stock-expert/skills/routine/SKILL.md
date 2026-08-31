---
name: routine
description: Run the full persisted Stock Expert routine workflow in a local or Codex Cloud workspace, then verify SQLite persistence and git status. Use when the user says /routine, routine pls, do the routine, stock expert routine, or asks for the daily persisted BIST routine.
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

1. Confirm the repository root and read `memory.md`,
   `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
2. If this is Cloud and the user supplied a workspace ZIP, import it first
   with `import-workspace-bundle --replace-database`; if no bundle was supplied,
   report that the run starts with the Cloud task's fresh/branch-specific
   SQLite state.
3. Assume the live root CSVs have already been refreshed or published. Do not
   silently refresh data as part of this skill.

## Command

Local:

```powershell
D:\miniconda3\python.exe -m stock_expert routine
```

Cloud:

```bash
python3 -m stock_expert routine
```

## Verification

After the command finishes:

1. Verify the printed `snapshot_id`, `review_run_id`, and related
   `review_pick_results` rows in the active SQLite database.
2. Run `git status --short`.
3. If local continuity is wanted after a Cloud run, export a bundle with
   `export-workspace-bundle`; do not commit the ZIP.

## Summary

Keep the handoff short. Report the pick basket, review result, snapshot/review
ids, signal and target/review dates, SQLite verification result, and
`git status --short`. Do not expand into strategy analysis unless requested.
