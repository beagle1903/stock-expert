from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / ".codex" / "hooks" / "validate_docs_update.py"


def run_validator(
    *changed_files: str,
    hook_input: dict[str, object] | None = None,
    task_note: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT)]
    for path in changed_files:
        command.extend(["--changed-file", path])
    if task_note:
        command.extend(["--task-note", task_note])
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=json.dumps(hook_input or {}),
        capture_output=True,
        text=True,
        check=False,
    )


class DocsStopHookTests(unittest.TestCase):
    def test_blocks_development_change_without_documentation(self) -> None:
        result = run_validator("stock_expert/services.py")

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("stock_expert/services.py", payload["reason"])
        self.assertIn("docs/features/*.md", payload["reason"])
        self.assertIn("memory.md", payload["reason"])

    def test_allows_development_change_with_accepted_documentation(self) -> None:
        result = run_validator("stock_expert/services.py", "docs/features/picks.md")

        self.assertEqual(json.loads(result.stdout), {})

    def test_docs_scratch_does_not_satisfy_documentation_requirement(self) -> None:
        result = run_validator("stock_expert/services.py", "docs/scratch/notes.md")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")

    def test_configuration_change_requires_documentation(self) -> None:
        result = run_validator(".codex/hooks.json")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")

    def test_code_tests_schema_cli_and_root_configuration_require_documentation(self) -> None:
        paths = [
            "stock_expert/services.py",
            "tests/test_services.py",
            "schema/migration.sql",
            "stock_expert/cli.py",
            "pyproject.toml",
        ]

        for path in paths:
            with self.subTest(path=path):
                payload = json.loads(run_validator(path).stdout)
                self.assertEqual(payload["decision"], "block")

    def test_non_development_change_does_not_require_documentation(self) -> None:
        result = run_validator("README.md")

        self.assertEqual(json.loads(result.stdout), {})

    def test_task_note_marker_allows_documentation_free_change(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as note:
            note.write("DOCS_NOT_NEEDED: internal refactor only\n")
            note_path = note.name
        self.addCleanup(Path(note_path).unlink, missing_ok=True)

        result = run_validator("stock_expert/services.py", task_note=note_path)

        self.assertEqual(json.loads(result.stdout), {})

    def test_hook_input_marker_allows_documentation_free_change(self) -> None:
        result = run_validator(
            "stock_expert/services.py",
            hook_input={"last_assistant_message": "DOCS_NOT_NEEDED: internal refactor only"},
        )

        self.assertEqual(json.loads(result.stdout), {})

    def test_blocks_changed_python_file_with_likely_dead_code(self) -> None:
        fixture = REPO_ROOT / "stock_expert" / "_dead_code_hook_fixture.py"
        fixture.write_text(
            "import json\n\n"
            "def _unused_helper():\n"
            "    return 1\n",
            encoding="utf-8",
        )
        self.addCleanup(fixture.unlink, missing_ok=True)

        result = run_validator("stock_expert/_dead_code_hook_fixture.py", "docs/context/codex-hooks.md")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("Likely dead code", payload["reason"])
        self.assertIn("unused import 'json'", payload["reason"])
        self.assertIn("unused private function '_unused_helper'", payload["reason"])


if __name__ == "__main__":
    unittest.main()
