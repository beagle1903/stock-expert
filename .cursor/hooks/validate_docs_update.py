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


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        nested = content.get("text")
        if isinstance(nested, str):
            return nested
        return _text_from_content(content.get("content"))
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _text_from_content(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return ""


def _assistant_text(entry: object) -> str:
    if not isinstance(entry, dict):
        return ""
    role = entry.get("role") or entry.get("type")
    if role != "assistant":
        message = entry.get("message")
        if isinstance(message, dict) and (message.get("role") == "assistant"):
            return _text_from_content(message.get("content"))
        return ""
    message = entry.get("message")
    if isinstance(message, dict):
        text = _text_from_content(message.get("content"))
        if text:
            return text
    return _text_from_content(entry.get("content"))


def last_assistant_text_from_transcript(path: object) -> str:
    if not isinstance(path, str) or not path.strip():
        return ""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    last = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        text = _assistant_text(entry)
        if text:
            last = text
    return last


def last_assistant_text(hook_input: dict[str, object]) -> str:
    direct = hook_input.get("last_assistant_message")
    text = _text_from_content(direct)
    if text:
        return text
    transcript_text = last_assistant_text_from_transcript(hook_input.get("transcript_path"))
    if transcript_text:
        return transcript_text
    for key in MESSAGE_KEYS[1:]:
        value = hook_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def normalize_hook_input(hook_input: dict[str, object]) -> dict[str, object]:
    normalized = dict(hook_input)
    message = last_assistant_text(hook_input)
    if message:
        normalized["last_assistant_message"] = message
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
