# Workflow Rules

Canonical standing rules. Not optional. Not feature-only.

## Pull Requests

- After every completed development task, commit on a short topic branch, push, and open a GitHub pull request.
- Do not wait for the user to ask.
- Do not leave completed work local-only.
- Do not skip a PR because the change looks small or is just docs.
- The parent agent owns commits, issues, and PRs. `se-implement` does not commit unless the user already asked.
- This applies to every development task, including docs/workflow changes, not only large features.
- Tiny typo-only edits may still go directly to `main` when the scope is a single obvious typo. Everything else needs a PR.
- Return the PR URL when done.
- Follow existing GitHub PR conventions: `gh pr create` with a HEREDOC body that has Summary and Test plan.
- Do not prefix branches with `codex/`.

## Subagents

- Always dispatch project subagents. Do not skip them because a task looks small.
- The project agents live in `.claude/agents/se-*.md`.
- `se-explore` before a change when layout is unknown.
- `se-implement` for one scoped change.
- `se-strategy-review` after persistence, ranking, review, import, or snapshot work.
- `se-ui-review` after Evidence Console changes.
- Use `se-explore` instead of Claude Code's built-in `Explore` agent for this repo.
- Do not nest subagents.
- Do not invent a fifth project agent.
- `/code-review` and `/security-review` run only when the user asks.
- The parent owns issues, branches, commits, and PRs. `se-implement` does not commit unless the user already asked.
- The Cursor copies of these rules in `.cursor/rules/*.mdc` are leftovers awaiting removal under GitHub issue #36.

### Roster

- `se-explore` — read-only search before a change when the layout is unknown. Preferred model: haiku
- `se-implement` — one scoped change. Preferred model: inherit
- `se-strategy-review` — after persistence, ranking, review, import, or snapshot work. Preferred model: opus
- `se-ui-review` — after Evidence Console changes. Preferred model: sonnet

`inherit` means the parent session's model.

### Cascade

If the Agent call fails because the model is unavailable or rejected, retry with the Agent tool's `model` override in this order:

- se-explore: haiku → inherit
- se-implement: inherit only
- se-strategy-review: opus → sonnet → inherit
- se-ui-review: sonnet → inherit

Do not invent a fifth model. If inherit also fails, stop and ask the user.

### Reporting

After each subagent, report the actual model: the requested model, the model that ran if known, and whether that was a downgrade. A downgraded `se-strategy-review` remains a valid review unless the user says otherwise; do not silently re-run it on a stronger model.
