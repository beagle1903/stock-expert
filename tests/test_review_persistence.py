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
    get_candidate_outcomes,
    get_strategy_pilot_baskets,
    get_strategy_pilot_state,
    get_weights_as_of,
    init_db,
    insert_weights,
    persist_review_bundle,
    persist_strategy_pilot_review,
    ensure_strategy_pilot,
    replace_picks_and_strategy_pilot_baskets,
    replace_strategy_pilot_baskets,
)
from stock_expert.models import PickRow, PriceBar, Weights


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

    def _pilot_baskets(self) -> list[dict[str, object]]:
        return [
            {
                "strategy": "score_ranked",
                "ticker": "AAA",
                "selection_rank": 1,
                "candidate_rank": 1,
                "score": 1.0,
                "selection_bucket": "score_ranked",
            },
            {
                "strategy": "bucketed",
                "ticker": "BBB",
                "selection_rank": 1,
                "candidate_rank": 8,
                "score": 0.8,
                "selection_bucket": "coverage_recovery",
            },
        ]

    def _prepare_pilot(self) -> None:
        ensure_strategy_pilot(
            self.settings,
            signal_date=date(2026, 4, 20),
            weights=Weights(
                date=date(2026, 4, 20),
                momentum_weight=0.4,
                volume_weight=0.6,
            ),
        )
        replace_strategy_pilot_baskets(
            self.settings,
            snapshot_id=7,
            signal_date=date(2026, 4, 20),
            target_trade_date=date(2026, 4, 21),
            basket_rows=self._pilot_baskets(),
        )

    def _pilot_target_prices(self, include_bucketed: bool = True) -> dict[str, PriceBar]:
        prices = {
            "AAA": PriceBar(
                ticker="AAA",
                date=date(2026, 4, 21),
                open_price=100.0,
                close_price=100.0,
                volume=1_000_000,
            )
        }
        if include_bucketed:
            prices["BBB"] = PriceBar(
                ticker="BBB",
                date=date(2026, 4, 21),
                open_price=100.0,
                close_price=105.0,
                volume=1_000_000,
            )
        return prices

    def test_pilot_state_and_dual_baskets_round_trip(self) -> None:
        self._prepare_pilot()

        state = get_strategy_pilot_state(self.settings)
        baskets = get_strategy_pilot_baskets(self.settings, snapshot_id=7)

        self.assertIsNotNone(state)
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["started_signal_date"], "2026-04-20")
        self.assertEqual(state["momentum_weight"], 0.4)
        self.assertEqual(state["volume_weight"], 0.6)
        self.assertEqual(
            [(row["strategy"], row["ticker"], row["candidate_rank"]) for row in baskets],
            [("bucketed", "BBB", 8), ("score_ranked", "AAA", 1)],
        )

    def test_complete_paired_review_updates_outcomes_sessions_and_state(self) -> None:
        self._prepare_pilot()

        persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.0,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
            candidate_outcomes=self._outcomes(),
            signal_snapshot_id=7,
            pilot_target_prices=self._pilot_target_prices(),
        )

        state = get_strategy_pilot_state(self.settings)
        baskets = get_strategy_pilot_baskets(self.settings, snapshot_id=7)
        with connect(self.settings) as conn:
            sessions = conn.execute(
                """
                SELECT strategy, pick_count, evaluated_count, wins, avg_return, is_complete
                FROM strategy_pilot_sessions
                ORDER BY strategy
                """
            ).fetchall()

        basket_by_ticker = {row["ticker"]: row for row in baskets}
        self.assertEqual(state["completed_sessions"], 1)
        self.assertEqual(state["bucketed_session_wins"], 1)
        self.assertEqual(state["compounded_edge"], 0.05)
        self.assertEqual(basket_by_ticker["AAA"]["return_pct"], 0.0)
        self.assertEqual(basket_by_ticker["BBB"]["return_pct"], 0.05)
        self.assertEqual(
            [
                (
                    row["strategy"],
                    row["pick_count"],
                    row["evaluated_count"],
                    row["wins"],
                    row["avg_return"],
                    row["is_complete"],
                )
                for row in sessions
            ],
            [
                ("bucketed", 1, 1, 1, 0.05, 1),
                ("score_ranked", 1, 1, 0, 0.0, 1),
            ],
        )

    def test_state_evaluation_ignores_sessions_before_pilot_start(self) -> None:
        self._prepare_pilot()
        with connect(self.settings) as conn:
            conn.executemany(
                """
                INSERT INTO strategy_pilot_sessions (
                    pilot_name, signal_snapshot_id, signal_date, review_date,
                    strategy, pick_count, evaluated_count, wins, avg_return,
                    is_complete
                )
                VALUES (
                    'bucketed-default-v1', 6, '2026-04-19', '2026-04-20',
                    ?, 1, 1, 0, ?, 1
                )
                """,
                [
                    ("score_ranked", 0.0),
                    ("bucketed", -0.5),
                ],
            )

        persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.0,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(
                date=date(2026, 4, 21),
                momentum_weight=0.4,
                volume_weight=0.6,
            ),
            candidate_outcomes=self._outcomes(),
            signal_snapshot_id=7,
            pilot_target_prices=self._pilot_target_prices(),
        )

        state = get_strategy_pilot_state(self.settings)
        self.assertEqual(state["status"], "active")
        self.assertEqual(state["completed_sessions"], 1)
        self.assertEqual(state["compounded_edge"], 0.05)

    def test_incomplete_paired_review_does_not_advance_state(self) -> None:
        self._prepare_pilot()

        persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.0,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
            candidate_outcomes=self._outcomes(),
            signal_snapshot_id=7,
            pilot_target_prices=self._pilot_target_prices(include_bucketed=False),
        )

        state = get_strategy_pilot_state(self.settings)
        with connect(self.settings) as conn:
            bucketed_session = conn.execute(
                """
                SELECT evaluated_count, is_complete
                FROM strategy_pilot_sessions
                WHERE strategy = 'bucketed'
                """
            ).fetchone()

        self.assertEqual(state["completed_sessions"], 0)
        self.assertEqual(state["bucketed_session_wins"], 0)
        self.assertEqual(bucketed_session["evaluated_count"], 0)
        self.assertEqual(bucketed_session["is_complete"], 0)

    def test_standalone_incomplete_pilot_review_is_visible_and_idempotent(self) -> None:
        self._prepare_pilot()

        first_created = persist_strategy_pilot_review(
            self.settings,
            signal_snapshot_id=7,
            review_date=date(2026, 4, 21),
            target_prices={},
        )
        second_created = persist_strategy_pilot_review(
            self.settings,
            signal_snapshot_id=7,
            review_date=date(2026, 4, 21),
            target_prices=self._pilot_target_prices(),
        )

        state = get_strategy_pilot_state(self.settings)
        baskets = get_strategy_pilot_baskets(self.settings, snapshot_id=7)
        with connect(self.settings) as conn:
            sessions = conn.execute(
                """
                SELECT strategy, evaluated_count, is_complete
                FROM strategy_pilot_sessions
                ORDER BY strategy
                """
            ).fetchall()

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(state["completed_sessions"], 0)
        self.assertTrue(all(row["review_date"] == "2026-04-21" for row in baskets))
        self.assertTrue(all(row["return_pct"] is None for row in baskets))
        self.assertEqual(
            [
                (row["strategy"], row["evaluated_count"], row["is_complete"])
                for row in sessions
            ],
            [
                ("bucketed", 0, 0),
                ("score_ranked", 0, 0),
            ],
        )

    def test_reviewed_pilot_baskets_cannot_be_replaced(self) -> None:
        self._prepare_pilot()
        persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.0,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(
                date=date(2026, 4, 21),
                momentum_weight=0.4,
                volume_weight=0.6,
            ),
            candidate_outcomes=self._outcomes(),
            signal_snapshot_id=7,
            pilot_target_prices=self._pilot_target_prices(),
        )

        with self.assertRaisesRegex(
            ValueError,
            "reviewed pilot basket is immutable",
        ):
            replace_strategy_pilot_baskets(
                self.settings,
                snapshot_id=7,
                signal_date=date(2026, 4, 20),
                target_trade_date=date(2026, 4, 21),
                basket_rows=[
                    {
                        "strategy": "score_ranked",
                        "ticker": "CHANGED",
                        "selection_rank": 1,
                        "candidate_rank": 1,
                        "score": 9.0,
                        "selection_bucket": "score_ranked",
                    }
                ],
            )

        baskets = get_strategy_pilot_baskets(self.settings, snapshot_id=7)
        basket_by_ticker = {row["ticker"]: row for row in baskets}
        self.assertEqual(set(basket_by_ticker), {"AAA", "BBB"})
        self.assertEqual(basket_by_ticker["BBB"]["return_pct"], 0.05)

    def test_signal_and_pilot_baskets_publish_atomically(self) -> None:
        ensure_strategy_pilot(
            self.settings,
            signal_date=date(2026, 4, 20),
            weights=Weights(
                date=date(2026, 4, 20),
                momentum_weight=0.4,
                volume_weight=0.6,
            ),
        )
        original_pick = PickRow(
            date=date(2026, 4, 20),
            ticker="AAA",
            score=1.0,
            momentum=0.9,
            volume=0.8,
            risk="high",
            selection_bucket="core_momentum",
        )
        replace_picks_and_strategy_pilot_baskets(
            self.settings,
            rows=[original_pick],
            target_date=date(2026, 4, 20),
            snapshot_id=7,
            signal_date=date(2026, 4, 20),
            target_trade_date=date(2026, 4, 21),
            basket_rows=self._pilot_baskets(),
        )
        changed_pick = PickRow(
            date=date(2026, 4, 20),
            ticker="CHANGED",
            score=9.0,
            momentum=1.0,
            volume=1.0,
            risk="high",
            selection_bucket="core_momentum",
        )

        with patch(
            "stock_expert.database._replace_strategy_pilot_baskets_conn",
            side_effect=RuntimeError("basket write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "basket write failed"):
                replace_picks_and_strategy_pilot_baskets(
                    self.settings,
                    rows=[changed_pick],
                    target_date=date(2026, 4, 20),
                    snapshot_id=7,
                    signal_date=date(2026, 4, 20),
                    target_trade_date=date(2026, 4, 21),
                    basket_rows=[
                        {
                            "strategy": "bucketed",
                            "ticker": "CHANGED",
                            "selection_rank": 1,
                            "candidate_rank": 1,
                            "score": 9.0,
                            "selection_bucket": "core_momentum",
                        }
                    ],
                )

        with connect(self.settings) as conn:
            persisted_picks = conn.execute(
                "SELECT ticker FROM picks WHERE snapshot_id = 7"
            ).fetchall()
        persisted_baskets = get_strategy_pilot_baskets(
            self.settings,
            snapshot_id=7,
        )
        self.assertEqual(
            [row["ticker"] for row in persisted_picks],
            ["AAA"],
        )
        self.assertEqual(
            {row["ticker"] for row in persisted_baskets},
            {"AAA", "BBB"},
        )

    def test_pilot_outcome_failure_rolls_back_entire_review_bundle(self) -> None:
        self._prepare_pilot()

        with patch(
            "stock_expert.database._insert_strategy_pilot_results_conn",
            side_effect=RuntimeError("pilot outcome failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pilot outcome failure"):
                persist_review_bundle(
                    self.settings,
                    as_of=date(2026, 4, 20),
                    review_date=date(2026, 4, 21),
                    avg_return=0.0,
                    win_rate=0.0,
                    picks=self._picks(),
                    weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
                    candidate_outcomes=self._outcomes(),
                    signal_snapshot_id=7,
                    pilot_target_prices=self._pilot_target_prices(),
                )

        state = get_strategy_pilot_state(self.settings)
        baskets = get_strategy_pilot_baskets(self.settings, snapshot_id=7)
        with connect(self.settings) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_runs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM weights").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidate_outcomes").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM strategy_pilot_sessions").fetchone()[0], 0)

        self.assertEqual(state["completed_sessions"], 0)
        self.assertTrue(all(row["return_pct"] is None for row in baskets))

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

    def test_candidate_outcomes_can_exclude_future_review_dates(self) -> None:
        persist_review_bundle(
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
        persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 22),
            review_date=date(2026, 4, 23),
            avg_return=-0.10,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 23), momentum_weight=0.5, volume_weight=0.5),
            candidate_outcomes=self._outcomes(score=9.0),
            signal_snapshot_id=9,
        )

        outcomes = get_candidate_outcomes(
            self.settings,
            limit_sessions=10,
            before_review_date=date(2026, 4, 23),
        )

        self.assertEqual([row["review_date"] for row in outcomes], ["2026-04-21"])
        self.assertEqual([row["score"] for row in outcomes], [1.0])


if __name__ == "__main__":
    unittest.main()
