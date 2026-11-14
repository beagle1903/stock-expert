# Documentation Stop Hook

Claude Code runs one validator at the end of every turn. It blocks completion when development files changed without a relevant Markdown update.

- Validator: `scripts/validate_docs_update.py`
- Hook registration: `.claude/settings.json` (project `Stop` hook)
- Tests: `tests/test_docs_stop_hook.py`

The validator lives in `scripts/` rather than `.claude/hooks/` so it is not tied to one tool's folder: the tests and the hook call it by one path.

The hook checks whether development files changed without a relevant Markdown update. It also blocks likely dead code in changed runtime or hook Python files before allowing completion. Development files include Python code, tests, schema files, CLI code, root configuration files, and files with a development suffix (`.py`, `.json`, `.toml`, `.yaml`, ...) under `scripts/` and `.claude/`.

Two per-machine Claude Code files are never gated: `.claude/settings.local.json` and `.claude/launch.json`. Skill and agent Markdown under `.claude/` is not gated either.

Accepted documentation locations:

- `docs/features/*.md`
- `docs/context/*.md`
- `docs/tasks/*.md`
- `memory.md`

`docs/scratch/*` is never accepted and must not be modified for this purpose.

## Claude Code

`.claude/settings.json` registers a project `Stop` hook:

```text
python "$CLAUDE_PROJECT_DIR/scripts/validate_docs_update.py"
```

Claude Code sends the Stop event JSON on stdin (including `last_assistant_message` and `transcript_path`) and reads the validator's stdout. `{"decision": "block", "reason": "..."}` keeps the session going with the reason as feedback; `{}` lets it stop. The validator changes to the repository root itself, so the session's working directory does not matter.

The validator looks up the `DOCS_NOT_NEEDED` marker in `last_assistant_message` when that field is a non-empty string; otherwise it reads the JSONL file named by `transcript_path` and uses the last assistant entry that has text. A marker in an earlier assistant message does not count, and a missing or malformed transcript is ignored.

The hook fires at the end of every turn, not only when a task is finished, so a turn that ends with code changed and no docs yet is blocked until docs are updated or the marker is given. It needs `python` on `PATH`. Review the hook under `/hooks` in a Claude Code session after pulling a change to it.

## Running It By Hand

Check one changed file without a hook payload:

```powershell
D:\miniconda3\python.exe scripts\validate_docs_update.py --changed-file stock_expert\services.py
```

Run hook tests with:

```powershell
D:\miniconda3\python.exe -m unittest tests.test_docs_stop_hook -v
```

## Behavior

At Stop, the validator reads the hook JSON from stdin and discovers changed files from:

- Unstaged git changes
- Staged git changes
- Untracked files
- Commits between the current branch and its upstream merge base

When development files changed without accepted documentation, it returns a blocking message listing the development files and documentation locations to update.

When changed `stock_expert/*.py` or `scripts/*.py` files contain obvious dead code, the validator returns a blocking message first. The dead-code check uses Python `ast` from the standard library and currently flags unused imports plus unused top-level private functions/classes. Remove the unused code before finishing, or add real usage or test coverage if the item is intentionally retained.

Documentation-free work is allowed only with a deliberate marker and short reason:

```text
DOCS_NOT_NEEDED: internal refactor with no behavior or workflow impact
```

Place the marker in the final assistant message. The validator also accepts it in `docs/tasks/current.md`, but the marker anywhere in that file switches the gate off for every change until it is removed and makes the hook tests fail, so that file should only describe the marker in words.

## Limitations

- The hook verifies that accepted Markdown changed, not that the content is semantically sufficient.
- Stop hook input does not provide a stable changed-file list, so git state is the source of truth.
- Changes already committed and pushed to the tracked upstream may no longer be visible to the validator.
- Repositories without git metadata or an upstream can only validate working-tree changes.
- The hook does not replace code review, tests, or durable documentation judgment.

## Leftover Codex and Cursor entry points (removed in GitHub issue #36, step 6)

Two older entry points still call the same validator until their folders are deleted:

- Codex: `.codex/hooks.json`
- Cursor: `.cursor/hooks.json` through the adapter `.cursor/hooks/validate_docs_update.py`; see `docs/context/cursor-operator.md`

Until then the validator also gates development files under `.codex/` and `.cursor/` the same way as `scripts/` and `.claude/`, runs the dead-code check on `.cursor/hooks/*.py`, and leaves skill and agent Markdown under `.cursor/` ungated.

Codex discovers `.codex/hooks.json` automatically when the project `.codex/` layer is trusted. Hooks are enabled by default, but non-managed command hooks do not run until their exact definition is reviewed and trusted.

1. Start a new Codex session in the repository root.
2. Open `/hooks`.
3. Review the project-local Stop hook command and validator source.
4. Trust the hook definition.
5. Repeat the review after any hook configuration or script change because trust is tied to the hook hash.
