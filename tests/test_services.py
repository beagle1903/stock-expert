from __future__ import annotations

import json
import unittest
import uuid
from datetime import date
from pathlib import Path
import shutil
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.services import next_weekday, previous_weekday, review_output


class ServiceDateTests(unittest.TestCase):
    def test_next_weekday_skips_weekend(self) -> None:
        self.assertEqual(next_weekday(date(2026, 4, 24)), date(2026, 4, 27))

    def test_previous_weekday_skips_weekend(self) -> None:
        self.assertEqual(previous_weekday(date(2026, 4, 27)), date(2026, 4, 24))


class ReviewOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"review_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def test_dry_run_review_does_not_persist(self) -> None:
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.get_prices_for_date", return_value=[]),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=None),
            patch("stock_expert.services.insert_weights") as insert_weights,
            patch("stock_expert.services.insert_review_run") as insert_review_run,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=True))

        insert_weights.assert_not_called()
        insert_review_run.assert_not_called()
        self.assertTrue(payload["dry_run"])
        self.assertIsNone(payload["review_run_id"])

    def test_normal_review_persists(self) -> None:
        recent_rows = [{"ticker": "AAA", "score": 1.0, "open_price": 10.0, "close_price": 11.0}]
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.get_pick_results", return_value=recent_rows),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=None),
            patch("stock_expert.services.insert_weights") as insert_weights,
            patch("stock_expert.services.insert_review_run", return_value=7) as insert_review_run,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        insert_weights.assert_called_once()
        insert_review_run.assert_called_once()
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["review_run_id"], 7)


if __name__ == "__main__":
    unittest.main()
