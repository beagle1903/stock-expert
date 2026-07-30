from __future__ import annotations

import unittest

from stock_expert.pilot import evaluate_pilot_sessions, operational_strategy


def paired_rows(
    score_returns: list[float],
    bucketed_returns: list[float],
    *,
    complete: bool = True,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (score_return, bucketed_return) in enumerate(
        zip(score_returns, bucketed_returns, strict=True),
        start=1,
    ):
        rows.extend(
            [
                {
                    "signal_snapshot_id": index,
                    "strategy": "score_ranked",
                    "avg_return": score_return,
                    "is_complete": 1 if complete else 0,
                },
                {
                    "signal_snapshot_id": index,
                    "strategy": "bucketed",
                    "avg_return": bucketed_return,
                    "is_complete": 1 if complete else 0,
                },
            ]
        )
    return rows


class PilotPolicyTests(unittest.TestCase):
    def test_stays_active_before_ten_sessions_when_guardrail_is_clear(self) -> None:
        result = evaluate_pilot_sessions(paired_rows([0.01, -0.01], [0.02, -0.005]))

        self.assertEqual(result.status, "active")
        self.assertEqual(result.completed_sessions, 2)
        self.assertEqual(result.bucketed_session_wins, 2)
        self.assertEqual(result.decision_reason, "pilot_active")

    def test_rolls_back_at_negative_three_point_compounded_edge(self) -> None:
        result = evaluate_pilot_sessions(paired_rows([0.0], [-0.03]))

        self.assertEqual(result.status, "rolled_back")
        self.assertEqual(result.compounded_edge, -0.03)
        self.assertEqual(result.decision_reason, "bucketed_trailing_guardrail")

    def test_promotes_after_ten_sessions_when_both_thresholds_pass(self) -> None:
        result = evaluate_pilot_sessions(paired_rows([0.0] * 10, [0.004] * 10))

        self.assertEqual(result.status, "promoted")
        self.assertEqual(result.completed_sessions, 10)
        self.assertEqual(result.bucketed_session_wins, 10)
        self.assertEqual(result.score_compounded_return, 0.0)
        self.assertEqual(result.bucketed_compounded_return, 0.040728)
        self.assertEqual(result.compounded_edge, 0.040728)
        self.assertEqual(result.decision_reason, "promotion_thresholds_met")

    def test_fails_after_ten_sessions_without_required_edge(self) -> None:
        result = evaluate_pilot_sessions(paired_rows([0.0] * 10, [0.001] * 10))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.bucketed_session_wins, 10)
        self.assertEqual(result.compounded_edge, 0.010045)
        self.assertEqual(result.decision_reason, "promotion_thresholds_not_met")

    def test_incomplete_pairs_do_not_advance_the_pilot(self) -> None:
        result = evaluate_pilot_sessions(paired_rows([0.0], [0.10], complete=False))

        self.assertEqual(result.status, "active")
        self.assertEqual(result.completed_sessions, 0)
        self.assertEqual(result.bucketed_session_wins, 0)
        self.assertEqual(result.compounded_edge, 0.0)

    def test_sessions_are_evaluated_by_signal_date_not_snapshot_id(self) -> None:
        rows = [
            {
                "signal_snapshot_id": 1,
                "signal_date": "2026-04-22",
                "strategy": "score_ranked",
                "avg_return": 0.0,
                "is_complete": 1,
            },
            {
                "signal_snapshot_id": 1,
                "signal_date": "2026-04-22",
                "strategy": "bucketed",
                "avg_return": 0.10,
                "is_complete": 1,
            },
            {
                "signal_snapshot_id": 10,
                "signal_date": "2026-04-21",
                "strategy": "score_ranked",
                "avg_return": 0.0,
                "is_complete": 1,
            },
            {
                "signal_snapshot_id": 10,
                "signal_date": "2026-04-21",
                "strategy": "bucketed",
                "avg_return": -0.03,
                "is_complete": 1,
            },
        ]

        result = evaluate_pilot_sessions(rows)

        self.assertEqual(result.status, "rolled_back")
        self.assertEqual(result.completed_sessions, 1)
        self.assertEqual(result.bucketed_compounded_return, -0.03)

    def test_operational_strategy_uses_score_only_for_terminal_failures(self) -> None:
        self.assertEqual(operational_strategy(None), "bucketed")
        self.assertEqual(operational_strategy("active"), "bucketed")
        self.assertEqual(operational_strategy("promoted"), "bucketed")
        self.assertEqual(operational_strategy("rolled_back"), "score_ranked")
        self.assertEqual(operational_strategy("failed"), "score_ranked")


if __name__ == "__main__":
    unittest.main()
