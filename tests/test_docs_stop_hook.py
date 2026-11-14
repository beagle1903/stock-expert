from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_docs_update.py"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
TEST_TMP = REPO_ROOT / ".test_tmp"


def write_transcript(name: str, *entries: dict[str, object]) -> Path:
    TEST_TMP.mkdir(exist_ok=True)
    path = TEST_TMP / name
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def stop_payload(transcript: Path, **extra: object) -> dict[str, object]:
    return {
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": str(REPO_ROOT),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        **extra,
    }


def run_validator(
    *changed_files: str,
    hook_input: dict[str, object] | None = None,
    task_note: str | None = None,
    cwd: Path = REPO_ROOT,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT)]
    for path in changed_files:
        command.extend(["--changed-file", path])
    if task_note:
        command.extend(["--task-note", task_note])
    return subprocess.run(
        command,
        cwd=cwd,
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

        result = run_validator("stock_expert/_dead_code_hook_fixture.py", "docs/context/docs-stop-hook.md")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("Likely dead code", payload["reason"])
        self.assertIn("unused import 'json'", payload["reason"])
        self.assertIn("unused private function '_unused_helper'", payload["reason"])

    def test_blocks_changed_validator_script_with_likely_dead_code(self) -> None:
        fixture = REPO_ROOT / "scripts" / "_dead_code_hook_fixture.py"
        fixture.write_text("import json\n", encoding="utf-8")
        self.addCleanup(fixture.unlink, missing_ok=True)

        result = run_validator("scripts/_dead_code_hook_fixture.py", "docs/context/docs-stop-hook.md")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("unused import 'json'", payload["reason"])

    def test_validator_script_change_requires_documentation(self) -> None:
        result = run_validator("scripts/validate_docs_update.py")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("scripts/validate_docs_update.py", payload["reason"])

    def test_claude_overlay_change_requires_documentation(self) -> None:
        for path in (".claude/settings.json", ".claude/skills/bist/publish_capture.py"):
            with self.subTest(path=path):
                payload = json.loads(run_validator(path).stdout)
                self.assertEqual(payload["decision"], "block")
                self.assertIn(path, payload["reason"])

    def test_claude_local_only_files_do_not_require_documentation(self) -> None:
        result = run_validator(".claude/settings.local.json", ".claude/launch.json")

        self.assertEqual(json.loads(result.stdout), {})

    def test_claude_code_stop_payload_blocks_code_only_change(self) -> None:
        result = run_validator(
            "stock_expert/services.py",
            hook_input={
                "session_id": "test-session",
                "transcript_path": str(TEST_TMP / "missing.jsonl"),
                "cwd": str(REPO_ROOT),
                "hook_event_name": "Stop",
                "stop_hook_active": False,
                "last_assistant_message": "Updated services.py",
            },
        )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(set(payload), {"decision", "reason"})
        self.assertEqual(payload["decision"], "block")
        self.assertIn("stock_expert/services.py", payload["reason"])
        self.assertNotIn("followup_message", payload)

    def test_claude_code_stop_payload_marker_allows_stop(self) -> None:
        result = run_validator(
            "stock_expert/services.py",
            hook_input={
                "hook_event_name": "Stop",
                "stop_hook_active": True,
                "last_assistant_message": "DOCS_NOT_NEEDED: internal refactor only",
            },
        )

        self.assertEqual(json.loads(result.stdout), {})

    def test_validator_does_not_depend_on_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            blocked = run_validator("stock_expert/services.py", cwd=Path(outside))
            documented = run_validator(
                "stock_expert/services.py",
                "docs/features/picks.md",
                cwd=Path(outside),
            )

        self.assertEqual(json.loads(blocked.stdout)["decision"], "block")
        self.assertEqual(json.loads(documented.stdout), {})

    def test_claude_code_settings_register_validator_as_stop_hook(self) -> None:
        settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))

        commands = [
            hook["command"]
            for group in settings["hooks"]["Stop"]
            for hook in group["hooks"]
            if hook["type"] == "command"
        ]
        self.assertEqual(len(commands), 1)
        self.assertIn("$CLAUDE_PROJECT_DIR/scripts/validate_docs_update.py", commands[0])
        self.assertTrue(SCRIPT.is_file())

    def test_cursor_overlay_change_requires_documentation(self) -> None:
        result = run_validator(".cursor/hooks.json")

        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn(".cursor/hooks.json", payload["reason"])

    def test_stop_payload_allows_documented_change_with_transcript_present(self) -> None:
        transcript = write_transcript(
            "documented_change.jsonl",
            {"type": "assistant", "message": {"role": "assistant", "content": "Updated services.py"}},
        )

        result = run_validator(
            "stock_expert/services.py",
            "docs/context/docs-stop-hook.md",
            hook_input=stop_payload(transcript),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})

    def test_stop_payload_reads_marker_from_role_content_transcript(self) -> None:
        transcript = write_transcript(
            "docs_marker.jsonl",
            {"role": "user", "content": "change services"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Edit", "input": {}},
                    {"type": "text", "text": "DOCS_NOT_NEEDED: stop stdin has no message keys"},
                ],
            },
        )

        result = run_validator("stock_expert/services.py", hook_input=stop_payload(transcript))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})

    def test_stop_payload_reads_marker_from_claude_code_transcript(self) -> None:
        marker = "DOCS_NOT_NEEDED: internal refactor only"
        entries = (
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": marker}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": marker}},
        )
        for index, entry in enumerate(entries):
            with self.subTest(index=index):
                # The trailing tool-only assistant entry has no text, so it does not count as the last message.
                transcript = write_transcript(
                    "claude_code_marker.jsonl",
                    {"type": "user", "message": {"role": "user", "content": "change services"}},
                    entry,
                    {
                        "type": "assistant",
                        "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash"}]},
                    },
                )

                result = run_validator(
                    "stock_expert/services.py",
                    hook_input=stop_payload(transcript, stop_hook_active=True),
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout), {})

    def test_stop_payload_blocks_when_transcript_has_no_marker(self) -> None:
        transcript = write_transcript(
            "no_docs_marker.jsonl",
            {"type": "user", "message": {"role": "user", "content": "DOCS_NOT_NEEDED: says the user"}},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Updated services.py"}]},
            },
        )

        result = run_validator("stock_expert/services.py", hook_input=stop_payload(transcript))

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(set(payload), {"decision", "reason"})
        self.assertEqual(payload["decision"], "block")
        self.assertIn("stock_expert/services.py", payload["reason"])

    def test_stop_payload_ignores_marker_in_earlier_assistant_message(self) -> None:
        transcript = write_transcript(
            "stale_docs_marker.jsonl",
            {"role": "assistant", "content": [{"type": "text", "text": "DOCS_NOT_NEEDED: earlier turn"}]},
            {"role": "user", "content": "now change services"},
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Updated services.py"}]},
            },
        )

        result = run_validator("stock_expert/services.py", hook_input=stop_payload(transcript))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_last_assistant_message_takes_precedence_over_transcript(self) -> None:
        with_marker = write_transcript(
            "precedence_marker.jsonl",
            {"role": "assistant", "content": "DOCS_NOT_NEEDED: only in the transcript"},
        )
        without_marker = write_transcript(
            "precedence_no_marker.jsonl",
            {"role": "assistant", "content": "Updated services.py"},
        )

        blocked = run_validator(
            "stock_expert/services.py",
            hook_input=stop_payload(with_marker, last_assistant_message="Updated services.py"),
        )
        allowed = run_validator(
            "stock_expert/services.py",
            hook_input=stop_payload(without_marker, last_assistant_message="DOCS_NOT_NEEDED: internal refactor"),
        )
        empty_falls_back = run_validator(
            "stock_expert/services.py",
            hook_input=stop_payload(with_marker, last_assistant_message=""),
        )

        self.assertEqual(json.loads(blocked.stdout)["decision"], "block")
        self.assertEqual(json.loads(allowed.stdout), {})
        self.assertEqual(json.loads(empty_falls_back.stdout), {})

    def test_missing_or_malformed_transcript_blocks_without_crashing(self) -> None:
        malformed = write_transcript("malformed.jsonl")
        malformed.write_text(
            'not json DOCS_NOT_NEEDED\n{"role": "assistant", "content": "DOCS_NOT_NEEDED: trunc\n\n'
            '["assistant", "DOCS_NOT_NEEDED"]\n"DOCS_NOT_NEEDED"\nnull\n'
            '{"role": "assistant", "content": {"text": 5}}\n{"type": "assistant", "message": "DOCS_NOT_NEEDED"}\n',
            encoding="utf-8",
        )
        binary = TEST_TMP / "binary.jsonl"
        binary.write_bytes(b"\xff\xfe DOCS_NOT_NEEDED \x00\n")
        cases = {
            "missing": TEST_TMP / "missing.jsonl",
            "directory": TEST_TMP,
            "malformed": malformed,
            "binary": binary,
        }

        for name, transcript in cases.items():
            with self.subTest(name):
                result = run_validator("stock_expert/services.py", hook_input=stop_payload(transcript))

                payload = json.loads(result.stdout)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, "")
                self.assertEqual(payload["decision"], "block")

        for value in (None, 7, ["x"], ""):
            with self.subTest(transcript_path=value):
                result = run_validator(
                    "stock_expert/services.py",
                    hook_input={"hook_event_name": "Stop", "stop_hook_active": False, "transcript_path": value},
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
