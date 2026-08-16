# Codex Commands

## Project-Local Commands

This repository exposes a local Codex plugin through `.agents/plugins/marketplace.json`.

Plugin:

- `stock-expert`

Commands:

- `/stock-expert:refresh-data`
- `/stock-expert:routine`
- `/stock-expert:run`

Fallback text shortcuts:

- `/refresh-data`
- `/routine`
- `/run`

Autocomplete uses plugin-qualified command names. Use
`/stock-expert:refresh-data` to publish the validated live CSV bundle,
`/stock-expert:run` to open the web app, and `/stock-expert:routine` for a
direct persisted CLI run. Bare shortcuts are repo conventions, not separately
registered autocomplete commands.

## Data Refresh

`/stock-expert:refresh-data` runs the separate
`refresh-investing-csvs` preparation command, verifies all four published
files, then opens `http://127.0.0.1:5173/?view=runs` unless CLI-only output was
requested. It never confirms or runs the persisted routine.

## Web App Launcher

`/stock-expert:run` launches `frontend/scripts/dev.mjs`, which reuses a healthy
local app or starts only the missing Vite UI/loopback API component. It verifies
`http://127.0.0.1:5173/` and, by default,
`http://127.0.0.1:18765/api/health`, then opens the UI in Codex's built-in
browser. `STOCK_EXPERT_API_PORT` overrides the API port for both the process and
Vite proxy. Separate UI/API logs, component/launcher pids, launch-session state,
watchdog polls, and the final operator summary live in ignored `.test_tmp/`.

Every new or reused boot receives at least five minutes of launcher-owned
observation at a 20-second default interval. The watchdog compares direct and
proxied health/latest-picks responses, checks review endpoints and operational
basket invariants, and scans newly appended logs. It fails early after repeated
endpoint/semantic failures (or a logged runtime error) and records likely cause
plus relevant log tails in `web-watchdog-summary.json`. Test-only short timing
requires the explicit `STOCK_EXPERT_WATCHDOG_ALLOW_SHORT=1` guard.

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
