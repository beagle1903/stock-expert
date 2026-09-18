# Workflow Rules

Canonical standing rules. Not optional. Not feature-only.

## Pull Requests

- After every completed development task, commit on a topic branch, push, and open a GitHub pull request.
- Do not wait for the user to ask.
- The parent agent owns commits, issues, and PRs. `se-implement` does not commit unless the user already asked.
- This applies to every development task, including docs/workflow changes, not only large features.
- Tiny typo-only edits may still go directly to `main` when the scope is a single obvious typo. Everything else needs a PR.
- Return the PR URL when done.
- Follow existing GitHub PR conventions: `gh pr create` with a HEREDOC body that has Summary and Test plan.
- Do not prefix branches with `codex/`.

## Subagents

- Always dispatch project subagents. Do not skip them because a task looks small.
- Use `.cursor/agents/se-*.md` via `.cursor/rules/subagent-routing.mdc`.
- `se-explore` before a change when layout is unknown.
- `se-implement` for one scoped change.
- `se-strategy-review` after persistence, ranking, review, import, or snapshot work.
- `se-ui-review` after Evidence Console changes.
- Do not use Cursor built-in `explore`.
- Do not nest subagents.
- bugbot and security-review run only when the user asks.
- The parent owns issues, branches, commits, and PRs.
- After each subagent, report requested slug, model that ran if known, and whether that was a downgrade.
