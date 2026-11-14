---
name: console
description: Start or reuse and observe the Stock Expert web app (Evidence Console), verify its UI, API, proxy, logs, and persisted dashboard semantics for at least five minutes, then open it in the Claude desktop app's built-in browser. Use when the user says /console, run the web app, open the dashboard, open the Evidence Console, or asks to launch the Stock Expert frontend.
---

# Stock Expert Web App

Start the local Stock Expert web app and open it in the built-in browser pane.

This is the Claude Code port of the Cursor `/run` skill. It is named `console`
because Claude Code already has a built-in `run` skill.

## Preflight

1. Confirm the working directory is the repository root (it contains
   `stock_expert/` and `AGENTS.md`).
2. Read `memory.md`, `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
3. Resolve the API port from `STOCK_EXPERT_API_PORT`, defaulting to `18765`.
   Use `http://127.0.0.1:5173/` for the UI and the resolved port for
   `/api/health`.

## Start, Reuse, And Observe

1. Run `npm ci` in `frontend/` only when
   `frontend/node_modules/vite/bin/vite.js` is missing.
2. Start `node frontend/scripts/dev.mjs` from the repository root as a
   background command (the shell tool's `run_in_background`), redirecting
   launcher stdout/stderr to ignored `.test_tmp/` files. The launcher probes
   both components, reuses healthy processes, starts only missing components,
   and refuses to kill or duplicate an occupied port. Do not start the servers
   with `preview_start` and a `.claude/launch.json` name: that path skips the
   launcher-owned watchdog.
3. Read `.test_tmp/web-launch-session.json`. It records whether each component
   was started or reused plus discovered process ids and log paths.
4. Wait up to 60 seconds for both endpoints, then open the UI while
   `.test_tmp/web-watchdog-summary.json` reports `observing`.
5. Leave the launcher watchdog running for its production default of at least
   five minutes. It polls every 20 seconds and must check UI/API liveness,
   direct and Vite-proxied health, latest picks, latest review/history,
   operational-basket semantics, proxy alignment, and newly logged runtime
   errors. Never set `STOCK_EXPERT_WATCHDOG_ALLOW_SHORT=1` outside automated
   tests or an explicitly labeled smoke test.
6. Do not finish the task until the watchdog summary becomes `passed` or
   `failed`. The background launcher exits when the observation ends, with exit
   code 0 only for `passed`; wait for that exit rather than polling in a sleep
   loop. On failure, immediately report `likelyCause`, endpoint failures, and
   the included UI/API log tails. A healthy reused pair receives the same
   observation window.

## Open And Report

Use only the built-in browser (`mcp__Claude_Browser__*`): open
`http://127.0.0.1:5173/` with `preview_start` and its `url` parameter, or
`navigate` when the pane is already open. Do not open an external browser and
do not use Claude in Chrome. Inspect browser-console errors with
`read_console_messages`; this is complementary to the launcher-owned watchdog.
Keep healthy servers running, then report the URL, direct/proxied API health,
started/reused state, component process ids, observation duration/poll count,
and final watchdog result.
