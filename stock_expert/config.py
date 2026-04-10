from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    db_path: Path
    default_pick_count: int = 5
    review_window_days: int = 7
    low_liquidity_threshold: float = 1_000_000
    max_abs_momentum: float = 0.15
    max_volume_spike: float = 4.0


def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        db_path=data_dir / "stock_expert.db",
    )
