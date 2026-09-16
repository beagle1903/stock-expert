# Project Subagents Design

## Goal

Give this repository four project-scoped Cursor subagents plus an always-on
parent routing rule so delegated work follows Stock Expert invariants and uses
an explicit model cascade, with the actual model reported after each launch.

## Scope

- Add `.cursor/agents/se-explore.md`, `se-implement.md`,
  `se-strategy-review.md`, and `se-ui-review.md`.
- Add `.cursor/rules/subagent-routing.mdc` with `alwaysApply: true`.
- Record the roster, pins, and cascade in `docs/context/cursor-operator.md`
  and `memory.md`.
- Add `tests/test_project_subagents.py` as a stdlib `unittest` contract check.
- Do not change `stock_expert/` strategy, SQLite, or the Evidence Console.
- Do not start GitHub issue #11 in this work.
- Do not add `subagentStart` hooks, user-global `~/.cursor/agents/`, or new
  Python/test dependencies.

## Alternatives Considered

1. Pin preferred models in agent frontmatter and keep cascade/reporting in a
   project rule. Selected: Cursor may still swap models, so the rule is the
   operational guarantee.
2. Prompt-only agents with parent-passed Task models. Rejected: easier to
   forget, no pin when Cursor launches the agent directly.
3. Add a `subagentStart` hook to deny built-ins or log models. Rejected for
   now as extra machinery.

## Architecture

The parent chat remains the coordinator. It owns GitHub issues, feature
branches, commits, and whether work starts. Subagents get a self-contained
prompt and do not inherit chat history.

Custom agent names are prefixed `se-` so they do not collide with Cursor's
built-in `explore` type. Built-in `explore` is unused once `se-explore`
exists. `bugbot` and `security-review` still run only when the user asks.

Do not nest subagents. Level-2 launches are known to ignore model pins.

## Agents

| File | Role | Frontmatter |
| --- | --- | --- |
| `se-explore.md` | Read-only codebase search | `readonly: true`, `model: composer-2.5-fast` |
| `se-implement.md` | One scoped code change | `model: inherit` |
| `se-strategy-review.md` | Persistence, ranking, review evidence | `model: claude-opus-5-thinking-high` |
| `se-ui-review.md` | Evidence Console review | `model: claude-4-sonnet` |

Each file's `description` must say when the parent should delegate. Bodies
encode the invariants below. `se-implement` does not commit unless the user
already asked in that turn.

### se-explore

Find files, data flow, and current behavior. No edits and no
state-changing shell. Use before a change when the parent does not already
know the layout.

### se-implement

One scoped change on the current feature branch. Follow existing structure.
Prefer tests before new behavior. Update `docs/features/`, `docs/context/`,
`docs/tasks/`, or `memory.md`. Do not invent trading UI, live quotes, orders,
forecasts, or strategy changes made only to pretty-print the dashboard. Do
not start the next ticket.

### se-strategy-review

After persistence, ranking, review, import, or snapshot work. Block on
broken atomic publication, future leakage, rewritten review evidence,
dry-run vs `routine` confusion, or `main` DB use on a non-`main` branch.
Nits are optional.

### se-ui-review

After Evidence Console changes. Block on invented trading capabilities,
missing empty/partial/unavailable evidence states, or mutate paths outside
Data & Runs.

## Model Routing

Preferred pins match the agent table. Parent launches with the same slug
when the Task tool allows it.

If the Task call fails because the slug is missing or rejected:

1. `se-explore`: `composer-2.5-fast` → `inherit`
2. `se-implement`: `inherit` only
3. `se-strategy-review`: `claude-opus-5-thinking-high` → `claude-4-sonnet` → `inherit`
4. `se-ui-review`: `claude-4-sonnet` → `inherit`

Do not invent a fifth model. If `inherit` also fails, stop and ask the user.

Cursor may still silently swap on plan, quota, admin block, or Max Mode.
After each subagent the parent reports: requested model, model that actually
ran if known, and whether that was a downgrade. A swapped
`se-strategy-review` remains a valid review unless the user says otherwise.
Do not silently re-run it on a stronger model.

`inherit` means this parent chat's model (currently Cursor Grok 4.6).

## Testing

`tests/test_project_subagents.py` parses agent YAML frontmatter and the
routing rule with the standard library only. It asserts the four names, the
four preferred models, `se-explore` `readonly: true`, cascade steps, and
that the rule requires reporting the actual model. It does not launch
Cursor or call paid APIs.

## Documentation

Implementation updates `docs/context/cursor-operator.md` and `memory.md`.
This spec is the design record. No new GitHub issue.

## Out Of Scope

Hooks, user-global agents, changing built-in Bugbot/security-review,
Python/frontend product tests, and GitHub issue #11.
