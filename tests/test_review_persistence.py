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
    create_snapshot_run,
    get_candidate_outcomes,
    get_conflicting_review_runs,
    get_signal_window_coverage,
    get_strategy_pilot_baskets,
    get_strategy_pilot_state,
    get_weights_as_of,
    init_db,
    insert_weights,
    persist_review_bundle,
    persist_strategy_pilot_review,
    ensure_strategy_pilot,
    replace_picks_and_strategy_pilot_baskets,
    replace_picks_for_date,
    replace_strategy_pilot_baskets,
)
from stock_expert.models import PickRow, PriceBar, Weights
from stock_expert.signal_window import SignalWindowCoverage, assess_signal_window


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

    def _missed_movers(self, ticker: str = "BBB") -> list[dict[str, object]]:
        return [
            {
                "ticker": ticker,
                "close_change_return": 0.08,
                "classification": "actionable",
                "reason": "not_selected_by_score",
                "attribution": {
                    "data_status": "ranked_candidate",
                    "candidate_rank": 6,
                    "selection_note": "below_top_pick_cutoff",
                    "selection_bucket": "score_ranked",
                    "signals": {
                        "momentum": 0.7,
                        "volume": 0.6,
                        "technical": 0.04,
                        "fundamental": 0.01,
                        "quality": 0.02,
                        "setup_penalty": 0.03,
                        "ma_trend": 1.0,
                        "liquidity": 0.9,
                    },
                    "adjustments": {
                        "total_boost": 0.07,
                        "net_adjustment": 0.04,
                    },
                },
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

    def test_missed_movers_are_persisted_once_with_the_review_bundle(self) -> None:
        review_id, created = persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.05,
            win_rate=1.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
            candidate_outcomes=self._outcomes(),
            signal_snapshot_id=None,
            missed_movers=self._missed_movers(),
        )
        rerun_id, rerun_created = persist_review_bundle(
            self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=-0.05,
            win_rate=0.0,
            picks=self._picks(),
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.9, volume_weight=0.1),
            candidate_outcomes=self._outcomes(score=9.0),
            signal_snapshot_id=None,
            missed_movers=self._missed_movers(ticker="CHANGED"),
        )

        with connect(self.settings) as conn:
            review = conn.execute(
                "SELECT missed_movers_captured FROM review_runs WHERE id = ?",
                (review_id,),
            ).fetchone()
            movers = conn.execute(
                """
                SELECT ticker, mover_order, classification, reason, candidate_rank,
                       momentum, total_boost, net_adjustment
                FROM review_missed_mover_results
                WHERE review_run_id = ?
                """,
                (review_id,),
            ).fetchall()

        self.assertTrue(created)
        self.assertFalse(rerun_created)
        self.assertEqual(rerun_id, review_id)
        self.assertEqual(review["missed_movers_captured"], 1)
        self.assertEqual(len(movers), 1)
        self.assertEqual(movers[0]["ticker"], "BBB")
        self.assertEqual(movers[0]["mover_order"], 1)
        self.assertEqual(movers[0]["classification"], "actionable")
        self.assertEqual(movers[0]["reason"], "not_selected_by_score")
        self.assertEqual(movers[0]["candidate_rank"], 6)
        self.assertEqual(movers[0]["momentum"], 0.7)
        self.assertEqual(movers[0]["total_boost"], 0.07)
        self.assertEqual(movers[0]["net_adjustment"], 0.04)

    def test_missed_mover_insert_failure_rolls_back_the_review_bundle(self) -> None:
        with patch(
            "stock_expert.database._insert_review_missed_movers_conn",
            side_effect=RuntimeError("missed mover insert failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "missed mover insert failed"):
                persist_review_bundle(
                    self.settings,
                    as_of=date(2026, 4, 20),
                    review_date=date(2026, 4, 21),
                    avg_return=0.05,
                    win_rate=1.0,
                    picks=self._picks(),
                    weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
                    candidate_outcomes=self._outcomes(),
                    signal_snapshot_id=None,
                    missed_movers=self._missed_movers(),
                )

        with connect(self.settings) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_runs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_pick_results").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidate_outcomes").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_missed_mover_results").fetchone()[0], 0)

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

    def _seed_review(self, signal_date: date, review_date: date) -> int:
        review_id, created = persist_review_bundle(
            self.settings,
            as_of=signal_date,
            review_date=review_date,
            avg_return=0.05,
            win_rate=1.0,
            picks=self._picks(),
            weights=Weights(date=review_date, momentum_weight=0.6, volume_weight=0.4),
            candidate_outcomes=self._outcomes(),
            signal_snapshot_id=None,
        )
        self.assertTrue(created)
        return review_id

    def test_conflicting_review_runs_report_both_collision_directions(self) -> None:
        exact_id = self._seed_review(date(2026, 4, 22), date(2026, 4, 24))
        same_review_date_id = self._seed_review(date(2026, 4, 23), date(2026, 4, 24))
        same_signal_date_id = self._seed_review(date(2026, 4, 22), date(2026, 4, 27))
        self._seed_review(date(2026, 4, 20), date(2026, 4, 21))
        self._seed_review(date(2026, 4, 24), date(2026, 4, 27))

        rows = get_conflicting_review_runs(
            self.settings,
            signal_date=date(2026, 4, 22),
            review_date=date(2026, 4, 24),
        )

        self.assertEqual(
            [(row["id"], row["as_of_date"], row["review_date"]) for row in rows],
            [
                (same_review_date_id, "2026-04-23", "2026-04-24"),
                (same_signal_date_id, "2026-04-22", "2026-04-27"),
            ],
        )
        self.assertNotIn(exact_id, [row["id"] for row in rows])

    def test_conflicting_review_runs_is_empty_for_exact_key_and_unrelated_reviews(self) -> None:
        self._seed_review(date(2026, 4, 20), date(2026, 4, 21))
        self._seed_review(date(2026, 4, 21), date(2026, 4, 22))

        self.assertEqual(
            get_conflicting_review_runs(
                self.settings,
                signal_date=date(2026, 4, 20),
                review_date=date(2026, 4, 21),
            ),
            [],
        )
        self.assertEqual(
            get_conflicting_review_runs(
                self.settings,
                signal_date=date(2026, 4, 27),
                review_date=date(2026, 4, 28),
            ),
            [],
        )

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


class SignalWindowPersistenceTests(unittest.TestCase):
    SIGNAL_DATE = date(2026, 4, 20)

    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"signal_window_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.settings)
        ensure_strategy_pilot(
            self.settings,
            signal_date=self.SIGNAL_DATE,
            weights=Weights(date=self.SIGNAL_DATE, momentum_weight=0.4, volume_weight=0.6),
        )
        self.snapshot_id = create_snapshot_run(self.settings, self.SIGNAL_DATE, "daily_csv", "data")

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def _coverage(self, gap: bool) -> SignalWindowCoverage:
        # 2026-04-17 is a Friday session; the gapped history skips it.
        days = (
            ["2026-04-20", "2026-04-16", "2026-04-15", "2026-04-14", "2026-04-13", "2026-04-10"]
            if gap
            else ["2026-04-20", "2026-04-17", "2026-04-16", "2026-04-15", "2026-04-14", "2026-04-13"]
        )
        coverage = assess_signal_window(self.SIGNAL_DATE, [date.fromisoformat(day) for day in days])
        assert coverage is not None
        return coverage

    def _pick(self, ticker: str) -> PickRow:
        return PickRow(
            date=self.SIGNAL_DATE,
            ticker=ticker,
            score=1.0,
            momentum=0.9,
            volume=0.8,
            risk="high",
            selection_bucket="score_ranked",
        )

    def _basket(self, ticker: str) -> list[dict[str, object]]:
        return [
            {
                "strategy": strategy,
                "ticker": ticker,
                "selection_rank": 1,
                "candidate_rank": 1,
                "score": 1.0,
                "selection_bucket": "score_ranked" if strategy == "score_ranked" else "core_momentum",
            }
            for strategy in ("score_ranked", "bucketed")
        ]

    def _publish(self, ticker: str, coverage: SignalWindowCoverage | None) -> None:
        replace_picks_and_strategy_pilot_baskets(
            self.settings,
            rows=[self._pick(ticker)],
            target_date=self.SIGNAL_DATE,
            snapshot_id=self.snapshot_id,
            signal_date=self.SIGNAL_DATE,
            target_trade_date=date(2026, 4, 21),
            basket_rows=self._basket(ticker),
            signal_window=coverage,
        )

    def _persisted_state(self) -> tuple[list[str], list[str], int]:
        with connect(self.settings) as conn:
            picks = [row["ticker"] for row in conn.execute("SELECT ticker FROM picks WHERE snapshot_id = ?", (self.snapshot_id,))]
            coverage_rows = conn.execute("SELECT COUNT(*) FROM signal_window_coverage").fetchone()[0]
        baskets = sorted({row["ticker"] for row in get_strategy_pilot_baskets(self.settings, snapshot_id=self.snapshot_id)})
        return picks, baskets, int(coverage_rows)

    def test_publication_stores_coverage_with_the_basket(self) -> None:
        self._publish("AAA", self._coverage(gap=True))

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)

        self.assertEqual(
            stored,
            {
                "snapshot_id": self.snapshot_id,
                "signal_date": "2026-04-20",
                "status": "gap",
                "window_bars": 6,
                "window_start": "2026-04-10",
                "window_end": "2026-04-20",
                "missing_sessions": ["2026-04-17"],
                "non_session_dates": [],
                "affected_components": ["momentum", "volume", "fade_then_rechase"],
            },
        )
        self.assertEqual(self._persisted_state(), (["AAA"], ["AAA"], 1))

    def test_coverage_is_none_when_the_publication_recorded_none(self) -> None:
        self._publish("AAA", None)

        self.assertIsNone(get_signal_window_coverage(self.settings, self.snapshot_id))
        self.assertEqual(self._persisted_state(), (["AAA"], ["AAA"], 0))

    def test_unreviewed_republish_replaces_the_coverage_row(self) -> None:
        self._publish("AAA", self._coverage(gap=True))
        self._publish("BBB", self._coverage(gap=False))

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)

        assert stored is not None
        self.assertEqual(stored["status"], "contiguous")
        self.assertEqual(stored["missing_sessions"], [])
        self.assertEqual(stored["affected_components"], [])
        self.assertEqual(self._persisted_state(), (["BBB"], ["BBB"], 1))

    def test_reviewed_basket_refusal_writes_neither_picks_nor_coverage(self) -> None:
        self._publish("AAA", None)
        persist_review_bundle(
            self.settings,
            as_of=self.SIGNAL_DATE,
            review_date=date(2026, 4, 21),
            avg_return=0.05,
            win_rate=1.0,
            picks=[{"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 105.0}],
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
            candidate_outcomes=[],
            signal_snapshot_id=self.snapshot_id,
            pilot_target_prices={
                "AAA": PriceBar(
                    ticker="AAA",
                    date=date(2026, 4, 21),
                    open_price=100.0,
                    close_price=105.0,
                    volume=1_000_000,
                )
            },
        )

        with self.assertRaisesRegex(ValueError, "reviewed pilot basket is immutable"):
            self._publish("CHANGED", self._coverage(gap=True))

        self.assertIsNone(get_signal_window_coverage(self.settings, self.snapshot_id))
        self.assertEqual(self._persisted_state(), (["AAA"], ["AAA"], 0))

    def _review_snapshot(self) -> None:
        # A review pinned to the snapshot without pilot outcomes, as for a
        # pre-pilot basket: the pilot baskets stay replaceable.
        persist_review_bundle(
            self.settings,
            as_of=self.SIGNAL_DATE,
            review_date=date(2026, 4, 21),
            avg_return=0.05,
            win_rate=1.0,
            picks=[{"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 105.0}],
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.4, volume_weight=0.6),
            candidate_outcomes=[],
            signal_snapshot_id=self.snapshot_id,
        )

    def _republish_for_date(self, ticker: str, coverage: SignalWindowCoverage | None) -> None:
        replace_picks_for_date(
            self.settings,
            [self._pick(ticker)],
            self.SIGNAL_DATE,
            snapshot_id=self.snapshot_id,
            signal_window=coverage,
        )

    def test_reviewed_snapshot_keeps_its_coverage_on_a_dated_republish(self) -> None:
        self._republish_for_date("AAA", self._coverage(gap=True))
        self._review_snapshot()

        # e.g. a manual `picks --date` for a pre-pilot, already-reviewed day.
        self._republish_for_date("CHANGED", self._coverage(gap=False))

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)
        assert stored is not None
        self.assertEqual(stored["status"], "gap")
        self.assertEqual(stored["missing_sessions"], ["2026-04-17"])
        self.assertEqual(self._persisted_state()[0], ["CHANGED"])

    def test_reviewed_snapshot_keeps_its_coverage_on_a_pilot_republish(self) -> None:
        self._publish("AAA", self._coverage(gap=True))
        self._review_snapshot()

        self._publish("CHANGED", self._coverage(gap=False))

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)
        assert stored is not None
        self.assertEqual(stored["status"], "gap")

    def test_reviewed_snapshot_without_coverage_gains_none_on_republish(self) -> None:
        self._republish_for_date("AAA", None)
        self._review_snapshot()

        self._republish_for_date("CHANGED", self._coverage(gap=True))
        self._publish("CHANGED", self._coverage(gap=True))

        self.assertIsNone(get_signal_window_coverage(self.settings, self.snapshot_id))

    def test_unreviewed_republish_without_coverage_clears_the_stale_row(self) -> None:
        for publish in (self._publish, self._republish_for_date):
            with self.subTest(publish=publish.__name__):
                publish("AAA", self._coverage(gap=True))
                self.assertIsNotNone(get_signal_window_coverage(self.settings, self.snapshot_id))

                publish("BBB", None)

                self.assertIsNone(get_signal_window_coverage(self.settings, self.snapshot_id))
                self.assertEqual(self._persisted_state()[0], ["BBB"])

    def test_reviewed_republish_without_coverage_keeps_the_row(self) -> None:
        self._publish("AAA", self._coverage(gap=True))
        self._review_snapshot()

        self._publish("BBB", None)
        self._republish_for_date("CCC", None)

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)
        assert stored is not None
        self.assertEqual(stored["status"], "gap")

    def test_coverage_write_failure_rolls_back_picks_and_baskets(self) -> None:
        self._publish("AAA", self._coverage(gap=False))

        with patch(
            "stock_expert.database._replace_signal_window_coverage_conn",
            side_effect=RuntimeError("coverage write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "coverage write failed"):
                self._publish("CHANGED", self._coverage(gap=True))

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)
        assert stored is not None
        self.assertEqual(stored["status"], "contiguous")
        self.assertEqual(self._persisted_state(), (["AAA"], ["AAA"], 1))

    def test_non_pilot_publication_stores_coverage_in_the_same_transaction(self) -> None:
        replace_picks_for_date(
            self.settings,
            [self._pick("AAA")],
            self.SIGNAL_DATE,
            snapshot_id=self.snapshot_id,
            signal_window=self._coverage(gap=True),
        )
        stored = get_signal_window_coverage(self.settings, self.snapshot_id)
        assert stored is not None
        self.assertEqual(stored["status"], "gap")

        with patch(
            "stock_expert.database._replace_signal_window_coverage_conn",
            side_effect=RuntimeError("coverage write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "coverage write failed"):
                replace_picks_for_date(
                    self.settings,
                    [self._pick("CHANGED")],
                    self.SIGNAL_DATE,
                    snapshot_id=self.snapshot_id,
                    signal_window=self._coverage(gap=False),
                )

        stored = get_signal_window_coverage(self.settings, self.snapshot_id)
        assert stored is not None
        self.assertEqual(stored["status"], "gap")
        self.assertEqual(self._persisted_state()[0], ["AAA"])

    def test_coverage_for_another_signal_date_is_refused_before_writing(self) -> None:
        other = assess_signal_window(date(2026, 4, 17), [date(2026, 4, 17), date(2026, 4, 16)])
        assert other is not None

        with self.assertRaisesRegex(ValueError, "cannot be published with the 2026-04-20 basket"):
            self._publish("AAA", other)
        with self.assertRaisesRegex(ValueError, "cannot be published with the 2026-04-20 basket"):
            replace_picks_for_date(
                self.settings,
                [self._pick("AAA")],
                self.SIGNAL_DATE,
                snapshot_id=self.snapshot_id,
                signal_window=other,
            )

        self.assertEqual(self._persisted_state(), ([], [], 0))

    def test_init_db_adds_the_table_to_an_existing_database(self) -> None:
        with connect(self.settings) as conn:
            conn.execute("DROP TABLE signal_window_coverage")

        init_db(self.settings)

        with connect(self.settings) as conn:
            columns = [row["name"] for row in conn.execute("PRAGMA table_info(signal_window_coverage)")]
        self.assertEqual(
            columns,
            [
                "snapshot_id",
                "signal_date",
                "status",
                "window_bars",
                "window_start",
                "missing_sessions_json",
                "non_session_dates_json",
                "affected_components_json",
            ],
        )
        self.assertIsNone(get_signal_window_coverage(self.settings, self.snapshot_id))


if __name__ == "__main__":
    unittest.main()
