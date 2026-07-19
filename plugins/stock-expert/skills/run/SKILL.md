---
name: run
description: Start or reuse the Stock Expert web app, verify its local UI and API, and open it in Codex's built-in browser. Use when the user says /run, stock-expert:run, run the web app, open the dashboard, or asks to launch the Stock Expert frontend.
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
3. Use `http://127.0.0.1:5173/` for the UI and
   `http://127.0.0.1:8765/api/health` for the routine API.

## Start Or Reuse

1. Probe both URLs. Reuse the app when both are healthy.
2. If only the API is healthy, start only Vite with
   `node frontend/node_modules/vite/bin/vite.js --host 127.0.0.1 --strictPort`.
3. If only the UI is healthy, start only the API with
   `D:\miniconda3\python.exe -m stock_expert.web_api --host 127.0.0.1 --port 8765`.
4. If neither endpoint is healthy:
   - Run `npm ci` in `frontend/` only when
     `frontend/node_modules/vite/bin/vite.js` is missing.
   - Create `.test_tmp/` when needed.
   - Start `node frontend/scripts/dev.mjs --host 127.0.0.1 --strictPort` as a
     hidden background process from the repository root.
5. Start every new process hidden, redirect its output to `.test_tmp/`, and
   record its process id there. Do not terminate or duplicate a healthy existing
   component.
6. Wait up to 60 seconds for both endpoints. On failure, report the relevant
   log tail and likely port conflict.

## Open And Report

Use the installed `browser:control-in-app-browser` skill to open
`http://127.0.0.1:5173/` in the built-in browser. Do not open an external
browser. Keep the server running, then report the URL, API health, whether it
was started or reused, and the process id when newly started.
