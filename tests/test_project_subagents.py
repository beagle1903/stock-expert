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

EXPECTED_AGENT_FILENAMES = frozenset(spec["filename"] for spec in AGENT_SPECS)

RULE_NEEDLES = (
    "alwaysApply: true",
    "se-explore",
    "se-implement",
    "se-strategy-review",
    "se-ui-review",
    "composer-2.5-fast",
    "claude-opus-5-thinking-high",
    "claude-4-sonnet",
    "Preferred model: inherit",
    "report the actual model",
    "- se-explore: composer-2.5-fast → inherit",
    "- se-implement: inherit only",
    "- se-strategy-review: claude-opus-5-thinking-high → claude-4-sonnet → inherit",
    "- se-ui-review: claude-4-sonnet → inherit",
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
    def test_agents_dir_contains_exactly_four_se_markdown_files(self) -> None:
        md_files = {path.name for path in AGENTS_DIR.glob("*.md")}
        self.assertEqual(md_files, EXPECTED_AGENT_FILENAMES)

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
