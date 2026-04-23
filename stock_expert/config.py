from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    db_path: Path
    default_pick_count: int = 5
    low_liquidity_threshold: float = 1_000_000
    max_abs_momentum: float = 0.15
    same_day_chase_threshold_pct: float = 8.0
    same_day_chase_penalty_per_pct: float = 0.03
    max_same_day_chase_penalty: float = 0.12


def _sanitize_branch_name(branch_name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in branch_name.strip().lower())
    return cleaned.strip("_")


def _load_dotenv(base_dir: Path) -> None:
    env_path = base_dir / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _default_db_path(base_dir: Path, data_dir: Path) -> Path:
    override = os.environ.get("STOCK_EXPERT_DB_PATH", "").strip()
    if override:
        override_path = Path(override).expanduser()
        if not override_path.is_absolute():
            override_path = base_dir / override_path
        return override_path
    try:
        branch_name = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        branch_name = ""
    if not branch_name or branch_name == "main":
        return data_dir / "stock_expert.db"
    sanitized = _sanitize_branch_name(branch_name)
    if not sanitized:
        return data_dir / "stock_expert.db"
    return data_dir / f"stock_expert_{sanitized}.db"


def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    _load_dotenv(base_dir)
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        db_path=_default_db_path(base_dir, data_dir),
    )
