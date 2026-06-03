from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


MARKER = "DOCS_NOT_NEEDED"
ACCEPTED_DOC_PREFIXES = ("docs/features/", "docs/context/", "docs/tasks/")
DEVELOPMENT_PREFIXES = ("stock_expert/", "tests/", ".codex/")
DEVELOPMENT_FILENAMES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "tox.ini",
}
DEVELOPMENT_SUFFIXES = {".py", ".sql", ".toml", ".json", ".yaml", ".yml", ".ini", ".cfg"}


def normalize(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def run_git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [normalize(line) for line in result.stdout.splitlines() if line.strip()]


def discover_changed_files() -> list[str]:
    changed = set(run_git("diff", "--name-only"))
    changed.update(run_git("diff", "--cached", "--name-only"))
    changed.update(run_git("ls-files", "--others", "--exclude-standard"))

    upstream = run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if upstream:
        merge_base = run_git("merge-base", "HEAD", upstream[0])
        if merge_base:
            changed.update(run_git("diff", "--name-only", merge_base[0], "HEAD"))
    return sorted(changed)


def is_accepted_documentation(path: str) -> bool:
    normalized = normalize(path)
    if normalized == "memory.md":
        return True
    return normalized.endswith(".md") and normalized.startswith(ACCEPTED_DOC_PREFIXES)


def is_development_file(path: str) -> bool:
    normalized = normalize(path)
    if normalized in DEVELOPMENT_FILENAMES:
        return True
    if Path(normalized).suffix.lower() == ".sql":
        return True
    if not normalized.startswith(DEVELOPMENT_PREFIXES):
        return False
    return Path(normalized).suffix.lower() in DEVELOPMENT_SUFFIXES


def contains_marker(text: str | None) -> bool:
    return bool(text and MARKER in text)


def task_note_has_marker(path: Path) -> bool:
    try:
        return contains_marker(path.read_text(encoding="utf-8"))
    except OSError:
        return False


def load_hook_input() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def validation_response(
    changed_files: list[str],
    hook_input: dict[str, object],
    task_note: Path,
) -> dict[str, str]:
    development_files = sorted(path for path in changed_files if is_development_file(path))
    if not development_files:
        return {}

    if any(is_accepted_documentation(path) for path in changed_files):
        return {}

    if task_note_has_marker(task_note) or contains_marker(str(hook_input.get("last_assistant_message", ""))):
        return {}

    listed = "\n".join(f"- {path}" for path in development_files)
    reason = (
        "Development files changed without a relevant Markdown documentation update:\n"
        f"{listed}\n\n"
        "Update at least one relevant file in docs/features/*.md, docs/context/*.md, "
        "docs/tasks/*.md, or memory.md. Do not use docs/scratch/*. "
        "If documentation is deliberately unnecessary, add a DOCS_NOT_NEEDED marker "
        "with a short reason to docs/tasks/current.md or the final assistant message."
    )
    return {"decision": "block", "reason": reason}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--task-note", default="docs/tasks/current.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed_files = [normalize(path) for path in args.changed_file] or discover_changed_files()
    response = validation_response(changed_files, load_hook_input(), Path(args.task_note))
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
