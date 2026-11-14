from __future__ import annotations

import unittest
from pathlib import Path

from tests.test_project_subagents import parse_frontmatter


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

# Claude Code operator skills. `console` is the port of the Cursor `/run`
# skill, renamed because Claude Code ships a built-in `run` skill.
SKILL_SPECS = {
    "bist": (
        "mcp__Claude_Browser__",
        "publish_capture.py",
        "python.exe -m stock_expert routine",
        "review_pick_results",
        "git status --short",
    ),
    "routine": (
        "python.exe -m stock_expert routine",
        "snapshot_id",
        "review_run_id",
        "review_pick_results",
        "git status --short",
        "Do not ask",
        "data/stock_expert_<branch>.db",
    ),
    "console": (
        "node frontend/scripts/dev.mjs",
        "frontend/node_modules/vite/bin/vite.js",
        ".test_tmp/web-launch-session.json",
        ".test_tmp/web-watchdog-summary.json",
        "STOCK_EXPERT_API_PORT",
        "STOCK_EXPERT_WATCHDOG_ALLOW_SHORT=1",
        "five minutes",
        "`passed` or\n   `failed`",
        "likelyCause",
        "mcp__Claude_Browser__",
        "http://127.0.0.1:5173/",
    ),
    "refresh-data": (
        ".claude/skills/bist/SKILL.md",
        "publish_capture.py",
        "Do not run `routine` automatically",
        "Do not bypass CAPTCHA",
        "UTF-8 BOM",
        "git status --short",
        ".claude/skills/console/SKILL.md",
        "http://127.0.0.1:5173/?view=runs",
        "mcp__Claude_Browser__",
    ),
}

OTHER_TOOL_NEEDLES = ("cursor-ide-browser", "Cursor's", "Codex", "C:\\Users", "D:\\miniconda3")


def read_skill(name: str) -> tuple[dict[str, object], str]:
    return parse_frontmatter((SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8"))


class ClaudeCodeSkillTests(unittest.TestCase):
    def test_skills_dir_contains_exactly_the_operator_skills(self) -> None:
        names = {path.parent.name for path in SKILLS_DIR.glob("*/SKILL.md")}
        self.assertEqual(names, set(SKILL_SPECS))

    def test_no_project_skill_shadows_the_built_in_run_skill(self) -> None:
        self.assertFalse((SKILLS_DIR / "run").exists())

    def test_skill_frontmatter_names_match_their_folders(self) -> None:
        for name in SKILL_SPECS:
            with self.subTest(name):
                fields, _ = read_skill(name)
                self.assertEqual(fields.get("name"), name)
                self.assertIn(f"/{name}", str(fields.get("description")))
                self.assertIn("Use when", str(fields.get("description")))

    def test_skills_keep_their_operator_contract(self) -> None:
        for name, needles in SKILL_SPECS.items():
            _, body = read_skill(name)
            for needle in needles:
                with self.subTest(skill=name, needle=needle):
                    self.assertIn(needle, body)

    def test_skills_carry_no_cursor_codex_or_machine_specific_paths(self) -> None:
        for name in SKILL_SPECS:
            _, body = read_skill(name)
            for needle in OTHER_TOOL_NEEDLES:
                with self.subTest(skill=name, needle=needle):
                    self.assertNotIn(needle, body)

    def test_refresh_data_never_runs_the_routine(self) -> None:
        _, body = read_skill("refresh-data")
        self.assertNotIn("python.exe -m stock_expert routine", body)

    def test_skills_reference_only_files_that_exist(self) -> None:
        paths = (
            ".claude/skills/bist/SKILL.md",
            ".claude/skills/bist/publish_capture.py",
            ".claude/skills/console/SKILL.md",
            "frontend/scripts/dev.mjs",
            "memory.md",
            "docs/tasks/current.md",
            "docs/context/project.md",
            "docs/rules/output.md",
        )
        for path in paths:
            with self.subTest(path):
                self.assertTrue((REPO_ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
