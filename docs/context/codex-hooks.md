# Codex Hooks

## Documentation Stop Hook

This repository includes a project-local Codex Stop hook:

- Configuration: `.codex/hooks.json`
- Validator: `.codex/hooks/validate_docs_update.py`
- Tests: `tests/test_docs_stop_hook.py`

The hook checks whether development files changed without a relevant Markdown update. Development files include Python code, tests, schema files, CLI code, configuration files, and project-local Codex hook files.

Accepted documentation locations:

- `docs/features/*.md`
- `docs/context/*.md`
- `docs/tasks/*.md`
- `memory.md`

`docs/scratch/*` is never accepted and must not be modified for this purpose.

## Installation And Trust

Codex discovers `.codex/hooks.json` automatically when the project `.codex/` layer is trusted. Hooks are enabled by default, but non-managed command hooks do not run until their exact definition is reviewed and trusted.

1. Start a new Codex session in the repository root.
2. Open `/hooks`.
3. Review the project-local Stop hook command and validator source.
4. Trust the hook definition.
5. Repeat the review after any hook configuration or script change because trust is tied to the hook hash.

The Windows command uses the project Python runtime:

```powershell
D:\miniconda3\python.exe .codex\hooks\validate_docs_update.py --changed-file stock_expert\services.py
```

Run hook tests with:

```powershell
D:\miniconda3\python.exe -m unittest tests.test_docs_stop_hook -v
```

## Behavior

At Stop, the validator reads Codex hook JSON from stdin and discovers changed files from:

- Unstaged git changes
- Staged git changes
- Untracked files
- Commits between the current branch and its upstream merge base

When development files changed without accepted documentation, it returns a blocking message listing the development files and documentation locations to update.

Documentation-free work is allowed only with a deliberate marker and short reason:

```text
DOCS_NOT_NEEDED: internal refactor with no behavior or workflow impact
```

Place the marker in `docs/tasks/current.md` or the final assistant message.

## Limitations

- The hook verifies that accepted Markdown changed, not that the content is semantically sufficient.
- Stop hook input does not provide a stable changed-file list, so git state is the source of truth.
- Changes already committed and pushed to the tracked upstream may no longer be visible to the validator.
- Repositories without git metadata or an upstream can only validate working-tree changes.
- The hook does not replace code review, tests, or durable documentation judgment.
