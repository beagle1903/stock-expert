---
name: run
description: Start or reuse and observe the Stock Expert web app, verify its UI, API, proxy, logs, and persisted dashboard semantics for at least five minutes, then open it in Codex's built-in browser. Use when the user says /run, stock-expert:run, run the web app, open the dashboard, or asks to launch the Stock Expert frontend.
metadata:
  priority: 8
  pathPatterns:
    - "frontend/package.json"
    - "frontend/scripts/dev.mjs"
    - "stock_expert/web_api.py"
  bashPatterns:
    - "npm run dev"
    - "scripts/dev.mjs"
---

# Stock Expert Web App

Start the local Stock Expert web app and open it in Codex's built-in browser.

## Preflight

1. Confirm the working directory is `C:\Users\burha\Documents\dev\stock expert`.
2. Read `memory.md`, `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
3. Resolve the API port from `STOCK_EXPERT_API_PORT`, defaulting to `18765`.
   Use `http://127.0.0.1:5173/` for the UI and the resolved port for
   `/api/health`.

## Start, Reuse, And Observe

1. Run `npm ci` in `frontend/` only when
   `frontend/node_modules/vite/bin/vite.js` is missing.
2. Start `node frontend/scripts/dev.mjs` as a hidden background process from the
   repository root, redirecting launcher stdout/stderr to ignored `.test_tmp/`
   files. The launcher probes both components, reuses healthy processes, starts
   only missing components, and refuses to kill or duplicate an occupied port.
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
   `failed`. On failure, immediately report `likelyCause`, endpoint failures,
   and the included UI/API log tails. A healthy reused pair receives the same
   observation window.

## Open And Report

Use the installed `browser:control-in-app-browser` skill to open
`http://127.0.0.1:5173/` in the built-in browser. Do not open an external
browser. Inspect browser-console errors when the browser exposes them; this is
complementary to the launcher-owned watchdog. Keep healthy servers running,
then report the URL, direct/proxied API health, started/reused state, component
process ids, observation duration/poll count, and final watchdog result.
