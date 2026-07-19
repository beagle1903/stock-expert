# Codex Commands

## Project-Local Commands

This repository exposes a local Codex plugin through `.agents/plugins/marketplace.json`.

Plugin:

- `stock-expert`

Commands:

- `/stock-expert:routine`
- `/stock-expert:run`

Fallback text shortcuts:

- `/routine`
- `/run`

Autocomplete uses plugin-qualified command names. Type `/stock-expert:routine`
or `/stock-expert:run` when selecting from the Codex command menu. Bare
`/routine` and `/run` are repo conventions for agents in this workspace, not
separately registered autocomplete commands.

## Web App Launcher

`/stock-expert:run` reuses a healthy local app or starts the Vite UI and
loopback routine API through `frontend/scripts/dev.mjs`. It verifies
`http://127.0.0.1:5173/` and `http://127.0.0.1:8765/api/health`, then opens the UI
in Codex's built-in browser. Runtime logs and the background process id live in
the ignored `.test_tmp/` directory.

The launcher does not terminate existing processes. In a partial UI/API state,
it starts only the missing component; an occupied unhealthy port is reported as
a conflict instead of killing its owner.

## Persisted Routine

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

Routine output must always include a labeled `Pick List:` section and a review
section so the actionable basket and previous-pick evaluation are visible without
searching through unlabeled JSON.

## Collaboration Artifact

The **Northbound** emblem selected for the user-level CodexCompass continuity
module is archived at `docs/assets/northbound-codex-emblem.png` so the original
gift has a version-controlled backup. It is documentation-only and is not
consumed by the Stock Expert runtime, frontend, or plugin.

![Northbound CodexCompass emblem](../assets/northbound-codex-emblem.png)
