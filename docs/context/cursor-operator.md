# Cursor Operator Overlay

Cursor is the current operator path for this repository. The Codex plugin and
Codex Stop hook remain in the repo as an unused fallback and are not the
documented daily workflow.

## Skills

Project skills live under `.cursor/skills/` and wrap existing CLI and launcher
behavior:

- `.cursor/skills/routine/SKILL.md` — persisted `routine`, then SQLite and
  `git status --short` verification
- `.cursor/skills/run/SKILL.md` — start or reuse `frontend/scripts/dev.mjs`,
  wait for the five-minute watchdog, open `http://127.0.0.1:5173/` in Cursor's
  in-app browser
- `.cursor/skills/refresh-data/SKILL.md` — refresh the four live Investing.com
  CSVs in Cursor's in-app browser, publish only a validated bundle, then open
  `http://127.0.0.1:5173/?view=runs`

Do not launch standalone Chrome or Edge for data refresh. Do not auto-run
`routine` after a refresh. The Codex copies under `plugins/stock-expert/skills/`
are leftover fallbacks.

## Documentation Stop Hook

- Configuration: `.cursor/hooks.json`
- Adapter: `.cursor/hooks/validate_docs_update.py`
- Shared validator: `.codex/hooks/validate_docs_update.py`
- Tests: `tests/test_docs_stop_hook.py`

The adapter runs the existing validator and maps Codex
`{"decision":"block","reason":"..."}` to Cursor stop output
`{"followup_message":"..."}`. Empty validator output stays `{}`.

`.cursor/` JSON, Python, and other development files are gated the same way as
`.codex/` files. Accepted documentation locations are unchanged:
`docs/features/`, `docs/context/`, `docs/tasks/`, and `memory.md`.

`failClosed` is not enabled yet. After the hook is trusted and Hooks output
shows the mapped JSON, set `"failClosed": true` on the `stop` entry.

## Trust And Verify

1. Open Cursor **Settings > Hooks** and review the project `stop` command.
2. Trust `.cursor/hooks.json` and `.cursor/hooks/validate_docs_update.py`.
3. Re-trust after any hook definition change.
4. Confirm a code-only edit produces a `followup_message` that lists the
   development files and accepted doc locations.
5. Confirm a matching docs update, or `DOCS_NOT_NEEDED:` in
   `docs/tasks/current.md` or the final assistant message, allows stop.

Run the tests with:

```powershell
D:\miniconda3\python.exe -m unittest tests.test_docs_stop_hook -v
```

## Conventions That Stay

- Feature branches remain `codex/<task-name>`
- `main` uses `data/stock_expert.db`; other branches stay isolated
- Codex docs in `docs/context/codex-commands.md` and
  `docs/context/codex-hooks.md` remain historical
