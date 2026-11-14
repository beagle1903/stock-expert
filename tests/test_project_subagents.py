from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob"})
REVIEW_TOOLS = READ_ONLY_TOOLS | {"Bash"}
WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})

# Each agent pins a model alias and a tool allow-list; `tools: None` means all tools.
# `body_needles` pin the instructions: every numbered step and constraint of an
# agent is covered by at least one phrase.
AGENT_SPECS = (
    {
        "filename": "se-explore.md",
        "name": "se-explore",
        "model": "haiku",
        "tools": READ_ONLY_TOOLS,
        "body_needles": (
            "read-only explorer",
            "Search and read only what is needed",
            "file paths, current behavior, and data flow",
            "No edits",
            "state-changing",
            "Do not invent trading, quotes, orders, or forecasts",
            "existing tests when explaining runtime behavior",
            "stop after describing where the change would go",
        ),
    },
    {
        "filename": "se-implement.md",
        "name": "se-implement",
        "model": "inherit",
        "tools": None,
        "body_needles": (
            "Stay on the current feature branch",
            "Do not start the next ticket",
            "Prefer tests before new behavior",
            "Avoid unrelated refactors",
            "`memory.md` when behavior changes",
            "does not commit unless",
            "Do not invent trading",
            "pretty-print the dashboard",
            "Keep snapshot publication atomic",
            "Do not leak future data into historical evidence",
            "other branches stay on branch databases",
            "Use the unittest suite and `--dry-run`",
            "do not close or rewrite an issue",
        ),
    },
    {
        "filename": "se-strategy-review.md",
        "name": "se-strategy-review",
        "model": "opus",
        "tools": REVIEW_TOOLS,
        "body_needles": (
            "Review only the persistence, ranking, review, import, or snapshot change",
            "atomic",
            "Block on broken atomic publication",
            "future leakage",
            "rewritten immutable review evidence",
            "dry-run vs `routine` confusion",
            "`data/stock_expert.db` on a non-`main` branch",
            "you do not edit files",
            "Never run `python -m stock_expert routine`",
            "Do not request unrelated refactors",
            "Critical, Important, or Nit",
            "no Critical or Important issues",
        ),
    },
    {
        "filename": "se-ui-review.md",
        "name": "se-ui-review",
        "model": "sonnet",
        "tools": REVIEW_TOOLS,
        "body_needles": (
            "Review only UI, dashboard adapter, or web presentation changes",
            "live quotes, orders, portfolios, forecasts, or target prices",
            "empty/partial/unavailable",
            "mutate paths outside Data & Runs",
            "signal-date versus target-trade-date",
            "you do not edit files",
            "Data & Runs",
            "Data & Runs is the only mutating web surface",
            "Critical, Important, or Nit",
            "no Critical or Important issues",
        ),
    },
)

EXPECTED_AGENT_FILENAMES = frozenset(spec["filename"] for spec in AGENT_SPECS)

CURSOR_ONLY_NEEDLES = ("readonly", "composer-2.5-fast", "claude-opus-5-thinking-high", "claude-4-sonnet", ".cursor")


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


class ClaudeCodeSubagentTests(unittest.TestCase):
    def test_claude_agents_dir_contains_exactly_the_four_se_agents(self) -> None:
        md_files = {path.name for path in AGENTS_DIR.glob("*.md")}
        self.assertEqual(md_files, EXPECTED_AGENT_FILENAMES)
        self.assertEqual(len(AGENT_SPECS), 4)

    def test_claude_agent_files_match_pinned_contract(self) -> None:
        for spec in AGENT_SPECS:
            with self.subTest(spec["filename"]):
                text = (AGENTS_DIR / spec["filename"]).read_text(encoding="utf-8")
                fields, body = parse_frontmatter(text)
                self.assertEqual(fields.get("name"), spec["name"])
                self.assertEqual(fields.get("model"), spec["model"])
                self.assertIsInstance(fields.get("description"), str)
                self.assertGreater(len(str(fields.get("description"))), 20)
                if spec["tools"] is None:
                    self.assertNotIn("tools", fields)
                else:
                    tools = {tool.strip() for tool in str(fields.get("tools")).split(",")}
                    self.assertEqual(tools, spec["tools"])
                    self.assertFalse(tools & WRITE_TOOLS)

    def test_claude_agents_keep_their_pinned_instructions(self) -> None:
        for spec in AGENT_SPECS:
            _, body = parse_frontmatter((AGENTS_DIR / spec["filename"]).read_text(encoding="utf-8"))
            for needle in spec["body_needles"]:
                with self.subTest(agent=spec["filename"], needle=needle):
                    self.assertIn(needle, body)

    def test_claude_agents_carry_no_cursor_only_settings(self) -> None:
        for path in sorted(AGENTS_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for needle in CURSOR_ONLY_NEEDLES:
                with self.subTest(agent=path.name, needle=needle):
                    self.assertNotIn(needle, text)

    def test_claude_reviewers_and_implementer_must_not_run_the_persisted_routine(self) -> None:
        for filename in ("se-implement.md", "se-strategy-review.md"):
            with self.subTest(filename):
                text = (AGENTS_DIR / filename).read_text(encoding="utf-8")
                self.assertIn("stock_expert routine", text)
                self.assertIn("writes", text)


WORKFLOW_RULES = REPO_ROOT / "docs" / "rules" / "workflow.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# The standing rules: subagent roster, model cascade, reporting, and always-PR.
# `docs/rules/workflow.md` carries the detail; `CLAUDE.md` is always loaded.
WORKFLOW_NEEDLES = (
    "Always dispatch project subagents",
    "se-explore",
    "se-implement",
    "se-strategy-review",
    "se-ui-review",
    "Preferred model: haiku",
    "Preferred model: inherit",
    "Preferred model: opus",
    "Preferred model: sonnet",
    "- se-explore: haiku → inherit",
    "- se-implement: inherit only",
    "- se-strategy-review: opus → sonnet → inherit",
    "- se-ui-review: sonnet → inherit",
    "report the actual model",
    "Do not invent a fifth model",
    "Do not nest subagents",
    "open a GitHub pull request",
    "Do not wait for the user to ask",
    "single obvious typo",
    "Summary and Test plan",
    "codex/",
)

WORKFLOW_FORBIDDEN_NEEDLES = ("composer-2.5-fast", "claude-opus-5-thinking-high", "claude-4-sonnet", "bugbot")

CLAUDE_MD_NEEDLES = (
    "pull request",
    "without waiting to be asked",
    "Always dispatch",
    "se-explore",
    "se-implement",
    "se-strategy-review",
    "se-ui-review",
    "docs/rules/workflow.md",
)


class ClaudeCodeStandingRulesTests(unittest.TestCase):
    def test_workflow_rules_encode_pr_roster_cascade_and_reporting(self) -> None:
        text = WORKFLOW_RULES.read_text(encoding="utf-8")
        for needle in WORKFLOW_NEEDLES:
            with self.subTest(needle):
                self.assertIn(needle, text)

    def test_workflow_roster_models_match_the_claude_agent_files(self) -> None:
        lines = WORKFLOW_RULES.read_text(encoding="utf-8").splitlines()
        for spec in AGENT_SPECS:
            with self.subTest(spec["filename"]):
                fields, _ = parse_frontmatter((AGENTS_DIR / spec["filename"]).read_text(encoding="utf-8"))
                self.assertEqual(fields.get("model"), spec["model"])
                prefix = f"- `{fields.get('name')}` — "
                roster = [line for line in lines if line.startswith(prefix)]
                self.assertEqual(len(roster), 1)
                self.assertTrue(roster[0].endswith(f"Preferred model: {fields.get('model')}"))

    def test_workflow_rules_carry_no_cursor_only_wording(self) -> None:
        text = WORKFLOW_RULES.read_text(encoding="utf-8")
        for needle in WORKFLOW_FORBIDDEN_NEEDLES:
            with self.subTest(needle):
                self.assertNotIn(needle, text)

    def test_claude_md_states_both_standing_rules(self) -> None:
        text = CLAUDE_MD.read_text(encoding="utf-8")
        for needle in CLAUDE_MD_NEEDLES:
            with self.subTest(needle):
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
