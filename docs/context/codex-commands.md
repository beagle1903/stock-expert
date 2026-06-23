# Codex Commands

## Project-Local Routine Command

This repository exposes a local Codex plugin through `.agents/plugins/marketplace.json`.

Plugin:

- `stock-expert`

Command:

- `/stock-expert:routine`

Fallback text shortcut:

- `/routine`

The command is a shortcut for the normal persisted routine workflow:

```powershell
D:\miniconda3\python.exe -m stock_expert routine
```

After running, it verifies SQLite persistence for the printed `snapshot_id`,
`review_run_id`, and related `review_pick_results`, then checks:

```powershell
git status --short
```

Codex may need a restart and the local plugin may need to be enabled from
`/plugins` before the slash command appears.
