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

A real Cursor `stop` payload includes `transcript_path`, not the final
assistant text. The adapter reads the last assistant entry from that
JSONL transcript (and still accepts `last_assistant_message` when present)
so `DOCS_NOT_NEEDED:` in the final reply reaches the shared validator.
The marker in `docs/tasks/current.md` remains valid.

`.cursor/` JSON, Python, and other development files are gated the same way as
`.codex/` files. Accepted documentation locations are unchanged:
`docs/features/`, `docs/context/`, `docs/tasks/`, and `memory.md`.

`failClosed` is not enabled yet. Set it only after the live follow-up in
the merge-vs-operator checks below has been seen once.

## Merge vs operator checks

The automated merge check is only:

```powershell
D:\miniconda3\python.exe -m unittest tests.test_docs_stop_hook -v
```

That already covers validator gating and adapter mapping. You do not need to
run `routine`, `/run`, or a data refresh to merge this overlay.

Remaining Cursor UI checks are one-time operator setup, not CI:

1. Open **Settings > Hooks** and trust the project `stop` command
   (`D:\miniconda3\python.exe .cursor/hooks/validate_docs_update.py`).
2. After that, the next real code-only agent turn should get a
   `followup_message`. A docs update or `DOCS_NOT_NEEDED:` in
   `docs/tasks/current.md` or the last assistant transcript entry should
   allow stop. Skip inventing a dummy edit just to prove this.
3. Re-trust after any hook definition change. `failClosed` stays off until
   that live follow-up has been seen once.

`/routine`, `/run`, and refresh-data still call the same CLI and
`frontend/scripts/dev.mjs`. Confirm by reading the skills; do not treat a
full 5-minute watchdog or live Investing.com scrape as part of this PR.

## Project Subagents

Project agents live under `.cursor/agents/` and are routed by
`.cursor/rules/subagent-routing.mdc` (`alwaysApply: true`).

| Agent | Job | Preferred model |
| --- | --- | --- |
| `se-explore` | Read-only codebase search | `composer-2.5-fast` |
| `se-implement` | One scoped change | `inherit` (parent chat) |
| `se-strategy-review` | Persistence/ranking/review review | `claude-opus-5-thinking-high` |
| `se-ui-review` | Evidence Console review | `claude-4-sonnet` |

If a Task slug is rejected: `se-explore` falls back
`composer-2.5-fast → inherit`; `se-implement` stays `inherit`;
`se-strategy-review` falls back
`claude-opus-5-thinking-high → claude-4-sonnet → inherit`;
`se-ui-review` falls back `claude-4-sonnet → inherit`. Do not invent a
fifth model. After each launch, report the actual model. Do not nest
subagents. Contract tests: `tests/test_project_subagents.py`.

## Requirement tickets

GitHub issues are the requirement tickets (currently #10–#14 open; #9 closed).
Leave them until that work starts. When a feature begins or ships, update the
matching issue or open a new one. `docs/tasks/` is the implementation record,
not a replacement for the issue.

## Conventions That Stay

- Feature branches remain `codex/<task-name>`
- `main` uses `data/stock_expert.db`; other branches stay isolated
- Codex docs in `docs/context/codex-commands.md` and
  `docs/context/codex-hooks.md` remain historical
