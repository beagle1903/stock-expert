from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / ".codex" / "hooks" / "validate_docs_update.py"
MESSAGE_KEYS = ("last_assistant_message", "text", "message", "response", "agent_message")


def load_hook_input() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def normalize_hook_input(hook_input: dict[str, object]) -> dict[str, object]:
    if isinstance(hook_input.get("last_assistant_message"), str):
        return hook_input
    normalized = dict(hook_input)
    for key in MESSAGE_KEYS:
        value = hook_input.get(key)
        if isinstance(value, str):
            normalized["last_assistant_message"] = value
            return normalized
    return normalized


def map_validator_response(payload: dict[str, object]) -> dict[str, str]:
    if payload.get("decision") != "block":
        return {}
    reason = payload.get("reason")
    message = reason if isinstance(reason, str) else (
        "Development files changed without a relevant Markdown documentation update. "
        "Update docs/features, docs/context, docs/tasks, or memory.md, or add "
        "DOCS_NOT_NEEDED: with a short reason."
    )
    return {"followup_message": message}


def main() -> int:
    command = [sys.executable, str(VALIDATOR), *sys.argv[1:]]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=json.dumps(normalize_hook_input(load_hook_input())),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        sys.stderr.write(result.stderr or result.stdout)
        return 1
    if not isinstance(payload, dict):
        payload = {}
    print(json.dumps(map_validator_response(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
