from __future__ import annotations

import shutil
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.database import (
    connect,
    get_weights_as_of,
    init_db,
    insert_weights,
    persist_review_bundle,
)
from stock_expert.models import Weights


class ReviewPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"review_persistence_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.settings)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def _picks(self) -> list[dict[str, object]]:
        return [{"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 105.0}]

    def _outcomes(self, score: float = 1.0) -> list[dict[str, object]]:
        return [
            {
                "ticker": "AAA",
                "candidate_rank": 1,
                "score": score,
                "momentum": 0.9,
                "volume": 0.8,
                "technical": 0.0,
                "fundamental": 0.0,
                "quality": 0.0,
                "setup_penalty": 0.0,
                "selected_score_ranked": 1,
                "selected_bucketed": 0,
                "bucketed_bucket": None,
                "return_pct": 0.05,
                "won": 1,
            }
        ]

    def test_weights_as_of_excludes_future_rows(self) -> None:
        insert_weights(self.settings, Weights(date=date(2026, 4, 20), momentum_weight=0.6, volume_weight=0.4))
        insert_weights(self.settings, Weights(date=date(2026, 4, 22), momentum_weight=0.8, volume_weight=0.2))

        weights = get_weights_as_of(self.settings, date(2026, 4, 20))

        self.assertIsNotNone(weights)
        self.assertEqual(weights.date, date(2026, 4, 20))
        self.assertEqual(weights.momentum_weight, 0.6)

    def test_review_bundle_rolls_back_everything_when_outcomes_fail(self) -> None:
        with patch("stock_expert.database._insert_candidate_outcomes_conn", side_effect=RuntimeError("outcome failure")):
            with self.assertRaisesRegex(RuntimeError, "outcome failure"):
                persist_review_bundle(
                    self.settings,
                    as_of=date(2026, 4, 20),
                    review_date=date(2026, 4, 21),
                    avg_return=0.05,
                    win_rate=1.0,
                    picks=self._picks(),
                    weights=Weights(date=date(2026, 4, 21), momentum_weight=0.62, volume_weight=0.38),
                    candidate_outcomes=self._outcomes(),
                    signal_snapshot_id=7,
                )

        with connect(self.settings) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_runs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM weights").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidate_outcomes").fetchone()[0], 0)

    def test_review_bundle_rerun_preserves_original_candidate_evidence(self) -> None:
        first_id, first_created = persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.05,
            win_rate=1.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.62, volume_weight=0.38),
            candidate_outcomes=self._outcomes(score=1.0),
            signal_snapshot_id=7,
        )
        second_id, second_created = persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=-0.10,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
            candidate_outcomes=self._outcomes(score=9.0),
            signal_snapshot_id=99,
        )

        with connect(self.settings) as conn:
            outcome = conn.execute("SELECT score, review_run_id FROM candidate_outcomes").fetchone()
            review_count = conn.execute("SELECT COUNT(*) FROM review_runs").fetchone()[0]

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(second_id, first_id)
        self.assertEqual(review_count, 1)
        self.assertEqual(outcome["score"], 1.0)
        self.assertEqual(outcome["review_run_id"], first_id)


if __name__ == "__main__":
    unittest.main()
