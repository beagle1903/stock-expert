# Project Subagents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four project Cursor subagents, an always-on routing rule with a named model cascade, overlay contract tests, and operator docs — without changing strategy or UI code.

**Architecture:** Agent prompts and preferred models live in `.cursor/agents/se-*.md`. Cascade, reporting, and parent coordination live in `.cursor/rules/subagent-routing.mdc`. `tests/test_project_subagents.py` parses those files with the standard library and fails if pins, names, readonly, or cascade text drift.

**Tech Stack:** Cursor agent markdown, Cursor `.mdc` rules, Python 3.11+ `unittest`, no new dependencies.

## Global Constraints

- Custom agent names are exactly `se-explore`, `se-implement`, `se-strategy-review`, and `se-ui-review`.
- Preferred models are exactly `composer-2.5-fast`, `inherit`, `claude-opus-5-thinking-high`, and `claude-4-sonnet`.
- `se-explore` is `readonly: true`.
- Do not nest subagents.
- Do not change `stock_expert/` strategy, SQLite, or the Evidence Console.
- Do not start GitHub issue #11.
- Do not add `subagentStart` hooks, user-global agents, or new Python/test dependencies.
- Do not invent a fifth fallback model; if `inherit` fails, stop and ask the user.
- Skip `git commit` steps unless the user explicitly asked to commit.

---

### Task 1: Overlay Contract Tests

**Files:**
- Create: `tests/test_project_subagents.py`

**Interfaces:**
- Consumes: repo-root `.cursor/agents/*.md` and `.cursor/rules/subagent-routing.mdc`.
- Produces: `parse_frontmatter(text: str) -> dict[str, object]` and `AGENT_SPECS` used by later tasks.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_project_subagents.py` with this full file:

```python
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".cursor" / "agents"
ROUTING_RULE = REPO_ROOT / ".cursor" / "rules" / "subagent-routing.mdc"

AGENT_SPECS = (
    {
        "filename": "se-explore.md",
        "name": "se-explore",
        "model": "composer-2.5-fast",
        "readonly": True,
        "body_needles": ("No edits", "state-changing"),
    },
    {
        "filename": "se-implement.md",
        "name": "se-implement",
        "model": "inherit",
        "readonly": False,
        "body_needles": ("does not commit unless", "Do not invent trading"),
    },
    {
        "filename": "se-strategy-review.md",
        "name": "se-strategy-review",
        "model": "claude-opus-5-thinking-high",
        "readonly": False,
        "body_needles": ("future leakage", "atomic"),
    },
    {
        "filename": "se-ui-review.md",
        "name": "se-ui-review",
        "model": "claude-4-sonnet",
        "readonly": False,
        "body_needles": ("Data & Runs", "empty/partial/unavailable"),
    },
)

RULE_NEEDLES = (
    "alwaysApply: true",
    "se-explore",
    "se-implement",
    "se-strategy-review",
    "se-ui-review",
    "composer-2.5-fast",
    "claude-opus-5-thinking-high",
    "claude-4-sonnet",
    "inherit",
    "report the actual model",
    "composer-2.5-fast → inherit",
    "claude-opus-5-thinking-high → claude-4-sonnet → inherit",
    "claude-4-sonnet → inherit",
    "Do not invent a fifth model",
    "Do not nest subagents",
)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        raise ValueError("missing opening frontmatter fence")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("missing closing frontmatter fence")
    fields: dict[str, object] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = _parse_scalar(value.strip())
    return fields, parts[2]


def _parse_scalar(value: str) -> object:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


class ProjectSubagentTests(unittest.TestCase):
    def test_agent_files_match_pinned_contract(self) -> None:
        for spec in AGENT_SPECS:
            path = AGENTS_DIR / spec["filename"]
            with self.subTest(spec["filename"]):
                text = path.read_text(encoding="utf-8")
                fields, body = parse_frontmatter(text)
                self.assertEqual(fields.get("name"), spec["name"])
                self.assertEqual(fields.get("model"), spec["model"])
                self.assertIsInstance(fields.get("description"), str)
                self.assertGreater(len(str(fields.get("description"))), 20)
                if spec["readonly"]:
                    self.assertIs(fields.get("readonly"), True)
                else:
                    self.assertNotEqual(fields.get("readonly"), True)
                for needle in spec["body_needles"]:
                    self.assertIn(needle, body)

    def test_routing_rule_encodes_cascade_and_reporting(self) -> None:
        text = ROUTING_RULE.read_text(encoding="utf-8")
        for needle in RULE_NEEDLES:
            with self.subTest(needle):
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail because the files are missing**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents -v`

Expected: FAIL with `FileNotFoundError` for `.cursor/agents/se-explore.md` and/or `.cursor/rules/subagent-routing.mdc`.

- [ ] **Step 3: Do not create agent or rule files in this task**

Leave the tests failing. Later tasks add the files.

- [ ] **Step 4: Skip commit unless the user asked**

If committing:

```powershell
git add -- tests/test_project_subagents.py
git commit -m "test: add project subagent overlay contract"
```

### Task 2: Project Agent Prompts

**Files:**
- Create: `.cursor/agents/se-explore.md`
- Create: `.cursor/agents/se-implement.md`
- Create: `.cursor/agents/se-strategy-review.md`
- Create: `.cursor/agents/se-ui-review.md`
- Test: `tests/test_project_subagents.py`

**Interfaces:**
- Consumes: `AGENT_SPECS` filenames, names, models, readonly, and body needles from Task 1.
- Produces: four Cursor subagent markdown files the parent can launch by name.

- [ ] **Step 1: Re-run tests to confirm agents are still missing**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents.ProjectSubagentTests.test_agent_files_match_pinned_contract -v`

Expected: FAIL with `FileNotFoundError` for `.cursor/agents/se-explore.md`.

- [ ] **Step 2: Write the four agent files**

Create `.cursor/agents/se-explore.md`:

```markdown
---
name: se-explore
description: Read-only Stock Expert codebase search. Use proactively before a change when the parent does not already know the file layout, data flow, or current behavior.
readonly: true
model: composer-2.5-fast
---

You are a read-only explorer for the Stock Expert repository.

When invoked:
1. Search and read only what is needed to answer the parent.
2. Return file paths, current behavior, and data flow.
3. Do not edit files.
4. Do not run state-changing shell commands.

Constraints:
- This is a BIST CLI plus Evidence Console. Do not invent trading, quotes, orders, or forecasts.
- Prefer `memory.md`, `docs/context/`, and existing tests when explaining runtime behavior.
- If the question needs a code change, stop after describing where the change would go.
```

Create `.cursor/agents/se-implement.md`:

```markdown
---
name: se-implement
description: Implement one scoped Stock Expert change on the current feature branch. Use after the parent has a spec or plan and a single task to execute.
model: inherit
---

You are an implementer for one scoped Stock Expert change.

When invoked:
1. Stay on the current feature branch. Do not start the next ticket.
2. Prefer tests before new behavior.
3. Follow existing structure. Avoid unrelated refactors.
4. Update `docs/features/`, `docs/context/`, `docs/tasks/`, or `memory.md` when behavior changes.
5. Do not commit unless the user already asked in this turn.

Constraints:
- Do not invent trading UI, live quotes, orders, forecasts, or target prices.
- Do not change strategy only to pretty-print the dashboard.
- Keep snapshot publication atomic. Do not leak future data into historical evidence.
- `main` uses `data/stock_expert.db`; other branches stay on branch databases.
- GitHub issues remain the requirement tickets; do not close or rewrite an issue unless that work started.
```

Create `.cursor/agents/se-strategy-review.md`:

```markdown
---
name: se-strategy-review
description: Review persistence, ranking, review, import, or snapshot changes. Use immediately after those code changes land.
model: claude-opus-5-thinking-high
---

You are a Stock Expert strategy and persistence reviewer.

When invoked:
1. Review only the persistence, ranking, review, import, or snapshot change.
2. Block on broken atomic publication.
3. Block on future leakage into historical ranking or review windows.
4. Block on rewritten immutable review evidence.
5. Block on dry-run vs `routine` confusion.
6. Block on using `data/stock_expert.db` on a non-`main` branch.

Nits are optional. Do not request unrelated refactors.

Report findings as Critical, Important, or Nit. Approve only if there are no Critical or Important issues.
```

Create `.cursor/agents/se-ui-review.md`:

```markdown
---
name: se-ui-review
description: Review Evidence Console changes for read-only evidence semantics. Use immediately after frontend or web-API presentation changes.
model: claude-4-sonnet
---

You are a Stock Expert Evidence Console reviewer.

When invoked:
1. Review only UI, dashboard adapter, or web presentation changes.
2. Block on invented trading capabilities, live quotes, orders, portfolios, forecasts, or target prices.
3. Block on missing empty/partial/unavailable evidence states when data can be absent.
4. Block on mutate paths outside Data & Runs.
5. Confirm signal-date versus target-trade-date labeling stays explicit.

Nits are optional. Data & Runs is the only mutating web surface.

Report findings as Critical, Important, or Nit. Approve only if there are no Critical or Important issues.
```

- [ ] **Step 3: Run the agent contract test**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents.ProjectSubagentTests.test_agent_files_match_pinned_contract -v`

Expected: PASS. The routing-rule test may still fail until Task 3.

- [ ] **Step 4: Skip commit unless the user asked**

If committing:

```powershell
git add -- .cursor/agents/se-explore.md .cursor/agents/se-implement.md .cursor/agents/se-strategy-review.md .cursor/agents/se-ui-review.md
git commit -m "feat: add project Cursor subagent prompts"
```

### Task 3: Parent Routing Rule

**Files:**
- Create: `.cursor/rules/subagent-routing.mdc`
- Test: `tests/test_project_subagents.py`

**Interfaces:**
- Consumes: `RULE_NEEDLES` from Task 1, including the exact cascade arrows and `report the actual model`.
- Produces: always-on parent instructions for launch, fallback, and reporting.

- [ ] **Step 1: Re-run the routing test and confirm it fails**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents.ProjectSubagentTests.test_routing_rule_encodes_cascade_and_reporting -v`

Expected: FAIL with `FileNotFoundError` for `.cursor/rules/subagent-routing.mdc`.

- [ ] **Step 2: Write the routing rule**

Create `.cursor/rules/subagent-routing.mdc` with this exact content so the contract needles match:

```markdown
---
description: Stock Expert project subagent roster, model pins, cascade, and reporting
alwaysApply: true
---

# Project Subagent Routing

Use these project agents instead of Cursor's built-in `explore` type. Do not nest subagents. Do not start GitHub issue #11 from this overlay. bugbot and security-review run only when the user asks.

## Roster

- `se-explore` — read-only search before a change when the layout is unknown. Preferred model: composer-2.5-fast
- `se-implement` — one scoped change. Preferred model: inherit
- `se-strategy-review` — after persistence, ranking, review, import, or snapshot work. Preferred model: claude-opus-5-thinking-high
- `se-ui-review` — after Evidence Console changes. Preferred model: claude-4-sonnet

`inherit` means the parent chat model.

## Cascade

If the Task call fails because the slug is missing or rejected:

- se-explore: composer-2.5-fast → inherit
- se-implement: inherit only
- se-strategy-review: claude-opus-5-thinking-high → claude-4-sonnet → inherit
- se-ui-review: claude-4-sonnet → inherit

Do not invent a fifth model. If inherit also fails, stop and ask the user.

## Reporting

After each subagent, report the actual model: requested slug, model that ran if known, and whether that was a downgrade. Cursor may silently swap on plan, quota, admin block, or Max Mode. A swapped se-strategy-review remains a valid review unless the user says otherwise. Do not silently re-run it on a stronger model.

The parent owns issues, branches, and commits. se-implement does not commit unless the user already asked.
```

- [ ] **Step 3: Run the full overlay tests**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents -v`

Expected: both tests PASS.

- [ ] **Step 4: Skip commit unless the user asked**

If committing:

```powershell
git add -- .cursor/rules/subagent-routing.mdc
git commit -m "feat: add project subagent routing rule"
```

### Task 4: Operator Docs

**Files:**
- Modify: `docs/context/cursor-operator.md`
- Modify: `memory.md`
- Test: `tests/test_project_subagents.py` (no new assertions; docs are the stop-hook record)

**Interfaces:**
- Consumes: roster, pins, cascade, and reporting text from Task 3.
- Produces: durable operator memory so later chats do not rediscover the overlay.

- [ ] **Step 1: Confirm overlay tests still pass before docs edits**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents -v`

Expected: PASS.

- [ ] **Step 2: Add a Project Subagents section to `docs/context/cursor-operator.md`**

Insert before `## Requirement tickets`:

```markdown
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
```

- [ ] **Step 3: Record the decision in `memory.md`**

Add a Decisions row:

```markdown
| 2026-09-16 | Project Cursor agents `se-explore`, `se-implement`, `se-strategy-review`, and `se-ui-review` plus always-on routing with a named model cascade. | Keeps delegated work on Stock Expert invariants and reports silent Cursor model swaps instead of assuming the pin ran. |
```

Add a Workflows bullet under Cursor operator skills:

```markdown
- Project subagents: `.cursor/agents/se-*.md` routed by `.cursor/rules/subagent-routing.mdc`
```

Add a Change Log row:

```markdown
| 2026-09-16 | Recorded project subagents, preferred models, and fallback cascade. |
```

- [ ] **Step 4: Re-run overlay tests after docs edits**

Run: `D:\miniconda3\python.exe -m unittest tests.test_project_subagents -v`

Expected: PASS.

- [ ] **Step 5: Skip commit unless the user asked**

If committing:

```powershell
git add -- docs/context/cursor-operator.md memory.md
git commit -m "docs: record project subagent routing"
```

## Self-Review

- Spec coverage: four agents, routing rule, cascade, reporting, unittest, cursor-operator.md, memory.md, no #11, no hooks, no product-code changes — each has a task.
- Placeholder scan: no TBD/TODO; test and file bodies are complete.
- Type consistency: `parse_frontmatter`, `AGENT_SPECS`, and `RULE_NEEDLES` names match across tasks.
