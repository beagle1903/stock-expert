from __future__ import annotations

import json
import unittest
import uuid
from datetime import date
from pathlib import Path
import shutil
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.database import connect, get_candidate_outcomes, init_db, insert_review_run
from stock_expert.models import MarketSnapshot, PickRow, PriceBar, SignalRow, Weights
from stock_expert.services import (
    RankingContext,
    _attribution_for_pick,
    bucketed_strategy_comparison_output,
    cap_setup_penalty_for_strong_momentum,
    daily_summary,
    downside_risk_output,
    generate_bucketed_picks,
    generate_picks,
    market_context_for_dates,
    market_context_score_penalty,
    next_review_weights,
    next_weekday,
    picks_output,
    previous_weekday,
    rank_candidates,
    review_output,
    rolling_candidate_diagnostics,
    rolling_review_weights,
)
from stock_expert.signals import (
    compute_fundamental_adjustment,
    compute_quality_adjustment,
    compute_setup_penalty,
    compute_technical_adjustment,
    score_signal,
)


class ServiceDateTests(unittest.TestCase):
    def test_next_weekday_skips_weekend(self) -> None:
        self.assertEqual(next_weekday(date(2026, 4, 24)), date(2026, 4, 27))

    def test_previous_weekday_skips_weekend(self) -> None:
        self.assertEqual(previous_weekday(date(2026, 4, 27)), date(2026, 4, 24))

    def test_next_weekday_skips_user_confirmed_market_holiday(self) -> None:
        self.assertEqual(next_weekday(date(2026, 4, 30)), date(2026, 5, 4))
        self.assertEqual(next_weekday(date(2026, 5, 18)), date(2026, 5, 20))
        self.assertEqual(next_weekday(date(2026, 5, 26)), date(2026, 6, 1))

    def test_previous_weekday_skips_user_confirmed_market_holiday(self) -> None:
        self.assertEqual(previous_weekday(date(2026, 5, 4)), date(2026, 4, 30))
        self.assertEqual(previous_weekday(date(2026, 5, 20)), date(2026, 5, 18))
        self.assertEqual(previous_weekday(date(2026, 6, 1)), date(2026, 5, 26))

    def test_market_context_marks_political_shock_window(self) -> None:
        context = market_context_for_dates(date(2026, 5, 21), date(2026, 5, 22), date(2026, 5, 25), date(2026, 5, 26))

        self.assertEqual(
            [entry["tag"] for entry in context["tags"]],
            [
                "political_shock_session",
                "political_shock_follow_through",
                "political_shock_follow_through",
                "half_holiday_low_liquidity",
            ],
        )
        self.assertIn("exogenous political-shock", context["interpretation"])
        self.assertEqual(context["selection_policy"], "shock_mode_penalty")

    def test_half_holiday_uses_liquidity_policy_without_shock_penalty(self) -> None:
        context = market_context_for_dates(date(2026, 5, 26))

        self.assertEqual(context["selection_policy"], "reduced_liquidity")
        self.assertIn("low-liquidity", context["interpretation"])


class EnrichmentSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = MarketSnapshot(
            date=date(2026, 4, 21),
            ticker="AAA",
            company_name="AAA",
            last_price=10.0,
            high_price=11.0,
            low_price=9.5,
            daily_change_pct=6.0,
            volume=1_000_000,
            weekly_perf_pct=5.0,
            monthly_perf_pct=8.0,
            ytd_perf_pct=10.0,
            yearly_perf_pct=12.0,
            technical_hourly="Güçlü Al",
            technical_daily="Güçlü Al",
            technical_weekly="Al",
            technical_monthly="Nötr",
            avg_volume_3m=500_000,
            market_cap=12_000_000_000,
            beta=0.9,
            revenue=2_100_000_000,
            pe_ratio=12.0,
        )
        self.price = PriceBar(ticker="AAA", date=date(2026, 4, 21), open_price=9.0, close_price=10.0, volume=1_000_000)

    def test_technical_labels_produce_bounded_adjustment(self) -> None:
        self.assertGreater(compute_technical_adjustment(self.snapshot), 0.0)
        bearish = self.snapshot.__class__(**{**self.snapshot.__dict__, "technical_daily": "Güçlü Sat", "technical_weekly": "Sat"})
        self.assertLess(compute_technical_adjustment(bearish), 0.0)

    def test_quality_and_fundamental_adjustments_are_bounded(self) -> None:
        quality = compute_quality_adjustment(self.snapshot, self.price)
        fundamental = compute_fundamental_adjustment(self.snapshot)
        self.assertLessEqual(abs(quality), 0.05)
        self.assertLessEqual(abs(fundamental), 0.04)

    def test_setup_penalty_discounts_weak_snapshot_context(self) -> None:
        weak = self.snapshot.__class__(
            **{
                **self.snapshot.__dict__,
                "technical_daily": "Güçlü Sat",
                "technical_weekly": "Sat",
                "revenue": 0,
                "pe_ratio": -12,
            }
        )

        self.assertEqual(compute_setup_penalty(self.snapshot, self.price), 0.0)
        self.assertGreater(compute_setup_penalty(weak, self.price), 0.08)

    def test_setup_penalty_discounts_stretched_snapshot_context(self) -> None:
        stretched = self.snapshot.__class__(
            **{
                **self.snapshot.__dict__,
                "daily_change_pct": 9.2,
                "weekly_perf_pct": 22.0,
                "monthly_perf_pct": 34.0,
            }
        )

        self.assertEqual(compute_setup_penalty(stretched, self.price), 0.05)

    def test_strong_momentum_technical_context_caps_setup_penalty(self) -> None:
        strong = SignalRow(
            ticker="AAA",
            date=date(2026, 4, 21),
            momentum=0.92,
            volume_spike=0.8,
            technical=0.06,
            liquidity=1.0,
        )
        weak_technical = SignalRow(
            ticker="BBB",
            date=date(2026, 4, 21),
            momentum=0.92,
            volume_spike=0.8,
            technical=0.03,
            liquidity=1.0,
        )

        self.assertEqual(cap_setup_penalty_for_strong_momentum(strong, 0.075), 0.03)
        self.assertEqual(cap_setup_penalty_for_strong_momentum(weak_technical, 0.075), 0.075)

    def test_adjustments_do_not_overpower_bad_base_signal(self) -> None:
        weak = SignalRow(ticker="AAA", date=date(2026, 4, 21), momentum=0.1, volume_spike=0.1)
        strong = SignalRow(ticker="BBB", date=date(2026, 4, 21), momentum=0.9, volume_spike=0.9)
        weights = Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)
        weak_total = score_signal(weak, weights) + compute_technical_adjustment(self.snapshot) + compute_quality_adjustment(self.snapshot, self.price) + compute_fundamental_adjustment(self.snapshot)
        strong_total = score_signal(strong, weights)
        self.assertLess(weak_total, strong_total)

    def test_chase_penalty_still_reduces_enriched_score(self) -> None:
        from stock_expert.services import apply_same_day_chase_penalty

        enriched_score = 1.08
        penalized = apply_same_day_chase_penalty(self._settings_stub(), enriched_score, 10.0)
        self.assertLess(penalized, enriched_score)

    def test_market_context_score_penalty_flags_shock_downside(self) -> None:
        weak = self.snapshot.__class__(
            **{
                **self.snapshot.__dict__,
                "daily_change_pct": -5.2,
                "technical_hourly": "Sat",
                "technical_daily": "Sat",
            }
        )

        self.assertEqual(market_context_score_penalty(date(2026, 4, 21), weak), 0.0)
        self.assertEqual(market_context_score_penalty(date(2026, 5, 21), weak), 0.16)
        self.assertEqual(market_context_score_penalty(date(2026, 5, 26), weak), 0.0)

    def _settings_stub(self) -> Settings:
        return Settings(base_dir=Path("."), data_dir=Path("data"), db_path=Path("data/test.db"))


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
            patch("stock_expert.services.persist_review_bundle") as persist_review_bundle,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=True))

        insert_weights.assert_not_called()
        persist_review_bundle.assert_not_called()
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
            patch("stock_expert.services.persist_review_bundle", return_value=(7, True)) as persist_review_bundle,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        persist_review_bundle.assert_called_once()
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["review_run_id"], 7)

    def test_normal_review_recomputes_candidate_ranking_without_rewriting_picks(self) -> None:
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]) as generate_picks,
            patch("stock_expert.services.get_pick_results", return_value=[]),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=None),
        ):
            review_output(self.settings, date(2026, 4, 21), dry_run=False)

        generate_picks.assert_called_once_with(
            self.settings,
            date(2026, 4, 20),
            dry_run=True,
            ranking_context=None,
        )

    def test_review_win_rate_requires_four_percent_return(self) -> None:
        recent_rows = [
            {"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 103.0},
            {"ticker": "BBB", "score": 1.0, "open_price": 100.0, "close_price": 104.0},
        ]
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.get_pick_results", return_value=recent_rows),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=None),
            patch("stock_expert.services.persist_review_bundle", return_value=(7, True)),
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        self.assertEqual(payload["performance"]["avg_return"], 0.035)
        self.assertEqual(payload["performance"]["win_rate"], 0.5)
        self.assertEqual(payload["performance"]["min_win_return"], 0.04)
        self.assertEqual(payload["performance"]["pick_count"], 2)
        self.assertEqual(payload["performance"]["wins"], 1)

    def test_review_marks_missing_prior_picks_as_operational_gap(self) -> None:
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.get_pick_results", return_value=[]),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=None),
            patch("stock_expert.services.get_review_run", return_value=None),
            patch("stock_expert.services.insert_weights") as insert_weights,
            patch("stock_expert.services.persist_review_bundle") as persist_review_bundle,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        insert_weights.assert_not_called()
        persist_review_bundle.assert_not_called()
        self.assertIsNone(payload["review_run_id"])
        self.assertEqual(payload["performance"]["evaluation_status"], "no_prior_picks")
        self.assertIn("No persisted picks", payload["performance"]["note"])
        self.assertEqual(payload["performance"]["pick_count"], 0)
        self.assertEqual(payload["reviewed_picks"], [])

    def test_dry_run_missed_mover_uses_wide_candidate_attribution(self) -> None:
        top_picks = [
            PickRow(date=date(2026, 4, 20), ticker=f"AAA{i}", score=1.0 - i / 100, momentum=1.0, volume=1.0, risk="high")
            for i in range(5)
        ]
        wide_candidates = [
            PickRow(date=date(2026, 4, 20), ticker=f"AAA{i}", score=1.0 - i / 100, momentum=1.0, volume=1.0, risk="high")
            for i in range(59)
        ] + [
            PickRow(date=date(2026, 4, 20), ticker="BBB", score=0.4, momentum=0.8, volume=0.7, risk="high")
        ]
        movers = [
            {
                "ticker": "BBB",
                "date": "2026-04-21",
                "day_return": 0.08,
                "close_price": 10.0,
                "volume": self.settings.low_liquidity_threshold,
            }
        ]
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=top_picks),
            patch("stock_expert.services.rank_candidates", return_value=wide_candidates),
            patch("stock_expert.services.get_prices_for_date", return_value=[]),
            patch("stock_expert.services.get_top_movers", return_value=movers),
            patch("stock_expert.services.get_latest_weights", return_value=None),
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=True))

        attribution = payload["missed_actionable"][0]["attribution"]
        self.assertEqual(attribution["candidate_rank"], 60)
        self.assertEqual(attribution["selection_note"], "below_top_pick_cutoff")

    def test_review_includes_pick_and_missed_mover_attribution(self) -> None:
        recent_rows = [{"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 105.0}]
        candidates = [
            PickRow(
                date=date(2026, 4, 20),
                ticker="AAA",
                score=1.0,
                momentum=0.9,
                volume=0.8,
                risk="high",
                technical=0.04,
                fundamental=0.02,
                quality=0.01,
                setup_penalty=0.0,
                ma_trend=1.0,
                liquidity=1.0,
            ),
            PickRow(
                date=date(2026, 4, 20),
                ticker="BBB",
                score=0.9,
                momentum=0.8,
                volume=0.7,
                risk="high",
                setup_penalty=0.05,
            ),
        ]
        movers = [
            {
                "ticker": "BBB",
                "date": "2026-04-21",
                "day_return": 0.08,
                "close_price": 10.0,
                "volume": self.settings.low_liquidity_threshold,
            }
        ]
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=candidates),
            patch("stock_expert.services.rank_candidates", return_value=candidates),
            patch("stock_expert.services.get_pick_results", return_value=recent_rows),
            patch("stock_expert.services.get_top_movers", return_value=movers),
            patch("stock_expert.services.get_latest_weights", return_value=None),
            patch("stock_expert.services.persist_review_bundle", return_value=(7, True)),
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        self.assertEqual(payload["reviewed_picks"][0]["ticker"], "AAA")
        self.assertEqual(payload["reviewed_picks"][0]["attribution"]["candidate_rank"], 1)
        self.assertEqual(payload["missed_actionable"][0]["ticker"], "BBB")
        self.assertEqual(payload["missed_actionable"][0]["attribution"]["selection_note"], "penalized_by_setup_context")

    def test_persisted_review_wins_require_four_percent_return(self) -> None:
        init_db(self.settings)
        picks = [
            {"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 103.99},
            {"ticker": "BBB", "score": 1.0, "open_price": 100.0, "close_price": 104.0},
        ]

        review_run_id = insert_review_run(
            settings=self.settings,
            as_of=date(2026, 4, 20),
            review_date=date(2026, 4, 21),
            avg_return=0.03995,
            win_rate=0.5,
            picks=picks,
            weights=Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4),
        )

        with connect(self.settings) as conn:
            review_run = conn.execute("SELECT wins FROM review_runs WHERE id = ?", (review_run_id,)).fetchone()
            pick_results = conn.execute(
                "SELECT ticker, won FROM review_pick_results WHERE review_run_id = ? ORDER BY ticker",
                (review_run_id,),
            ).fetchall()

        self.assertEqual(review_run["wins"], 1)
        self.assertEqual([(row["ticker"], row["won"]) for row in pick_results], [("AAA", 0), ("BBB", 1)])

    def test_normal_review_reuses_existing_run(self) -> None:
        recent_rows = [{"ticker": "AAA", "score": 1.0, "open_price": 10.0, "close_price": 11.0}]
        existing_review = {"id": 7, "momentum_weight": 0.63, "volume_weight": 0.37}
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.get_pick_results", return_value=recent_rows),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 4, 21), momentum_weight=0.63, volume_weight=0.37)),
            patch("stock_expert.services.get_review_run", return_value=existing_review),
            patch("stock_expert.services.persist_review_bundle", return_value=(7, False)) as persist_review_bundle,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        persist_review_bundle.assert_called_once()
        self.assertEqual(payload["review_run_id"], 7)
        self.assertEqual(payload["adjustments"]["momentum_weight"], 0.63)

    def test_persisted_review_records_ranked_candidate_outcomes(self) -> None:
        init_db(self.settings)
        candidates = [
            PickRow(date=date(2026, 4, 20), ticker="AAA", score=1.0, momentum=0.9, volume=0.8, risk="high"),
            PickRow(date=date(2026, 4, 20), ticker="BBB", score=0.9, momentum=0.8, volume=0.7, risk="high", setup_penalty=0.03),
        ]
        prices = [
            PriceBar(ticker="AAA", date=date(2026, 4, 21), open_price=100.0, close_price=105.0, volume=1_000_000),
            PriceBar(ticker="BBB", date=date(2026, 4, 21), open_price=100.0, close_price=110.0, volume=1_000_000),
        ]
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.generate_bucketed_picks", return_value=[candidates[1]]),
            patch("stock_expert.services.rank_candidates", return_value=candidates),
            patch("stock_expert.services.get_pick_results", return_value=[{"ticker": "AAA", "score": 1.0, "open_price": 100.0, "close_price": 105.0}]),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_top_movers", return_value=[]),
            patch("stock_expert.services.get_latest_weights", return_value=None),
            patch("stock_expert.services.get_review_run", return_value=None),
        ):
            review_output(self.settings, date(2026, 4, 21), dry_run=False)

        outcomes = get_candidate_outcomes(self.settings, limit_sessions=10)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes[0]["ticker"], "AAA")
        self.assertEqual(outcomes[0]["candidate_rank"], 1)
        self.assertEqual(outcomes[0]["selected_score_ranked"], 1)
        self.assertEqual(outcomes[1]["selected_bucketed"], 1)

    def test_rolling_candidate_diagnostics_compares_rank_bands_and_strategies(self) -> None:
        rows = [
            {"candidate_rank": 1, "return_pct": 0.05, "setup_penalty": 0.0, "technical": 0.06, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"candidate_rank": 8, "return_pct": 0.10, "setup_penalty": 0.03, "technical": 0.06, "selected_score_ranked": 0, "selected_bucketed": 1},
        ]

        payload = rolling_candidate_diagnostics(rows)

        self.assertEqual(payload["rank_bands"][0]["band"], "1-5")
        self.assertEqual(payload["rank_bands"][1]["band"], "6-20")
        self.assertEqual(payload["strategies"][0]["strategy"], "score_ranked")
        self.assertEqual(payload["strategies"][1]["strategy"], "bucketed")
        self.assertGreater(payload["strategies"][1]["avg_return"], payload["strategies"][0]["avg_return"])

    def test_rolling_candidate_diagnostics_recommends_best_cutoff_from_rank_bands(self) -> None:
        rows = [
            {"review_date": "2026-04-21", "candidate_rank": 1, "return_pct": -0.03, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"review_date": "2026-04-21", "candidate_rank": 2, "return_pct": -0.02, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"review_date": "2026-04-21", "candidate_rank": 3, "return_pct": -0.01, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"review_date": "2026-04-21", "candidate_rank": 4, "return_pct": 0.08, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 0, "selected_bucketed": 0},
            {"review_date": "2026-04-21", "candidate_rank": 5, "return_pct": 0.06, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 0, "selected_bucketed": 0},
            {"review_date": "2026-04-22", "candidate_rank": 1, "return_pct": -0.02, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"review_date": "2026-04-22", "candidate_rank": 2, "return_pct": -0.01, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"review_date": "2026-04-22", "candidate_rank": 3, "return_pct": 0.00, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 1, "selected_bucketed": 0},
            {"review_date": "2026-04-22", "candidate_rank": 4, "return_pct": 0.09, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 0, "selected_bucketed": 0},
            {"review_date": "2026-04-22", "candidate_rank": 5, "return_pct": 0.07, "setup_penalty": 0.0, "technical": 0.0, "selected_score_ranked": 0, "selected_bucketed": 0},
        ]

        payload = rolling_candidate_diagnostics(rows)

        self.assertEqual(payload["cutoff_analysis"]["best_cutoff"], "top_5")
        self.assertEqual(payload["cutoff_analysis"]["cutoffs"][0]["cutoff"], "top_3")
        self.assertEqual(payload["cutoff_analysis"]["cutoffs"][1]["cutoff"], "top_5")
        self.assertGreater(
            payload["cutoff_analysis"]["cutoffs"][1]["avg_return"],
            payload["cutoff_analysis"]["cutoffs"][0]["avg_return"],
        )

    def test_picks_output_includes_adjustments_block(self) -> None:
        pick = PickRow(
            date=date(2026, 4, 21),
            ticker="AAA",
            score=0.95,
            momentum=0.8,
            volume=0.7,
            technical=0.03,
            fundamental=0.02,
            quality=0.01,
            setup_penalty=0.02,
            ma_trend=0.6,
            liquidity=0.9,
            risk="medium",
        )
        snapshot = MarketSnapshot(date=date(2026, 5, 21), ticker="AAA", company_name="AAA", last_price=10, high_price=10, low_price=9, daily_change_pct=-5.2, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Sat", technical_daily="Al", technical_weekly="Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15)
        with (
            patch("stock_expert.services.generate_picks", return_value=[pick]),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=[snapshot]),
        ):
            payload = json.loads(picks_output(self.settings, date(2026, 5, 21), dry_run=True))

        self.assertEqual(payload["market_context"]["tags"][0]["tag"], "political_shock_session")
        self.assertIn("adjustments", payload["picks"][0])
        self.assertEqual(payload["picks"][0]["adjustments"]["market_context_score_penalty"], 0.14)
        self.assertEqual(payload["picks"][0]["adjustments"]["total_boost"], 0.06)
        self.assertEqual(payload["picks"][0]["adjustments"]["net_adjustment"], 0.04)
        self.assertEqual(payload["picks"][0]["signals"]["setup_penalty"], 0.02)
        self.assertEqual(payload["picks"][0]["selection_bucket"], "score_ranked")

    def test_picks_output_explains_breadth_reduced_exposure(self) -> None:
        prices = [
            PriceBar(ticker=f"AAA{i}", date=date(2026, 4, 21), open_price=10.0, close_price=9.0 if i < 4 else 11.0, volume=1_000_000)
            for i in range(5)
        ]
        with (
            patch("stock_expert.services.generate_picks", return_value=[]),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
        ):
            payload = json.loads(picks_output(self.settings, date(2026, 4, 21), dry_run=True))

        self.assertEqual(payload["exposure"]["advancer_ratio"], 0.2)
        self.assertEqual(payload["exposure"]["pick_count_cap"], 3)
        self.assertEqual(payload["exposure"]["policy"], "reduced_for_weak_breadth")

    def test_downside_risk_output_flags_same_day_drop_and_hourly_sell(self) -> None:
        picks = [
            PickRow(date=date(2026, 4, 21), ticker="SARKY", score=1.04, momentum=0.93, volume=1.0, risk="high"),
            PickRow(date=date(2026, 4, 21), ticker="GOOD", score=1.0, momentum=0.9, volume=0.9, risk="high"),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 4, 21), ticker="SARKY", company_name="SARKY", last_price=10, high_price=11, low_price=9, daily_change_pct=-7.71, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Sat", technical_daily="Güçlü Al", technical_weekly="Nötr", technical_monthly="Güçlü Al", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=20),
            MarketSnapshot(date=date(2026, 4, 21), ticker="GOOD", company_name="GOOD", last_price=10, high_price=11, low_price=9, daily_change_pct=2.0, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Al", technical_daily="Al", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=20),
        ]
        with (
            patch("stock_expert.services.generate_picks", return_value=picks) as generate_picks_mock,
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
        ):
            payload = json.loads(downside_risk_output(self.settings, date(2026, 4, 21)))

        generate_picks_mock.assert_called_once_with(
            self.settings,
            date(2026, 4, 21),
            dry_run=True,
            ranking_context=None,
        )
        self.assertEqual(payload["summary"]["pick_count"], 2)
        self.assertEqual(payload["summary"]["flagged_count"], 1)
        self.assertEqual(payload["summary"]["high_risk_count"], 1)
        self.assertEqual(payload["picks"][0]["ticker"], "SARKY")
        self.assertEqual(payload["picks"][0]["risk_level"], "high")
        self.assertEqual(
            payload["picks"][0]["downside_flags"],
            ["same_day_drop_below_5pct", "hourly_sell_signal"],
        )
        self.assertEqual(payload["picks"][1]["risk_level"], "low")
        self.assertIn("Reporting only", payload["selection_note"])

    def test_bucketed_strategy_comparison_evaluates_score_ranked_and_bucketed(self) -> None:
        score_ranked = [
            PickRow(date=date(2026, 4, 20), ticker="AAA", score=1.1, momentum=0.9, volume=0.8, risk="high", selection_bucket="score_ranked"),
            PickRow(date=date(2026, 4, 20), ticker="BBB", score=1.0, momentum=0.8, volume=0.7, risk="high", selection_bucket="score_ranked"),
        ]
        bucketed = [
            PickRow(date=date(2026, 4, 20), ticker="AAA", score=1.1, momentum=0.9, volume=0.8, risk="high", selection_bucket="core_momentum"),
            PickRow(date=date(2026, 4, 20), ticker="CCC", score=0.9, momentum=0.7, volume=0.9, risk="medium", selection_bucket="coverage_recovery"),
        ]
        prices = [
            PriceBar(ticker="AAA", date=date(2026, 4, 21), open_price=100.0, close_price=105.0, volume=1_000_000),
            PriceBar(ticker="BBB", date=date(2026, 4, 21), open_price=100.0, close_price=98.0, volume=1_000_000),
            PriceBar(ticker="CCC", date=date(2026, 4, 21), open_price=100.0, close_price=110.0, volume=1_000_000),
        ]
        with (
            patch("stock_expert.services.generate_picks", return_value=score_ranked),
            patch("stock_expert.services.generate_bucketed_picks", return_value=bucketed) as generate_bucketed_picks,
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
        ):
            payload = json.loads(bucketed_strategy_comparison_output(self.settings, date(2026, 4, 21)))

        self.assertEqual(payload["strategies"][0]["strategy"], "score_ranked")
        self.assertEqual(payload["strategies"][0]["wins"], 1)
        self.assertEqual(payload["strategies"][1]["strategy"], "bucketed")
        self.assertEqual(payload["strategies"][1]["wins"], 2)
        self.assertEqual(payload["overlap"]["bucketed_only"], ["CCC"])
        self.assertIn("persisted picks use score_ranked", payload["selection_note"])
        generate_bucketed_picks.assert_called_once_with(
            self.settings,
            date(2026, 4, 20),
            pick_count=len(score_ranked),
            ranking_context=None,
        )

    def test_attribution_explains_breadth_cap_exclusion(self) -> None:
        candidate = (
            3,
            PickRow(
                date=date(2026, 4, 20),
                ticker="AAA",
                score=0.8,
                momentum=0.8,
                volume=0.8,
                risk="high",
            ),
        )

        attribution = _attribution_for_pick(self.settings, candidate, effective_pick_count=2)

        self.assertEqual(attribution["selection_note"], "excluded_by_breadth_cap")

    def test_next_review_weights_reacts_to_results(self) -> None:
        current = Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)

        strong = next_review_weights(current, avg_return=0.02, win_rate=0.8, missed_actionable_count=0)
        weak = next_review_weights(current, avg_return=-0.01, win_rate=0.2, missed_actionable_count=6)

        self.assertEqual(strong.momentum_weight, 0.63)
        self.assertEqual(strong.volume_weight, 0.37)
        self.assertEqual(weak.momentum_weight, 0.55)
        self.assertEqual(weak.volume_weight, 0.45)

    def test_rolling_review_weights_requires_multiple_sessions(self) -> None:
        current = Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)
        weak_session = {"avg_return": -0.05, "win_rate": 0.0}

        unchanged = rolling_review_weights(current, [weak_session] * 4)
        adjusted = rolling_review_weights(current, [weak_session] * 5)

        self.assertEqual(unchanged.momentum_weight, 0.6)
        self.assertEqual(adjusted.momentum_weight, 0.58)


class OutputAndOrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"ordering_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def test_ranking_context_reuses_signal_date_ranking(self) -> None:
        context = RankingContext()
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=[]) as build_signals,
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
        ):
            generate_picks(
                self.settings,
                date(2026, 4, 21),
                dry_run=True,
                ranking_context=context,
            )
            rank_candidates(
                self.settings,
                date(2026, 4, 21),
                ranking_context=context,
            )

        build_signals.assert_called_once()

    def test_enrichment_reorders_close_candidates_but_not_strong_base_signal(self) -> None:
        signals = [
            SignalRow(ticker="AAA", date=date(2026, 4, 21), momentum=0.70, volume_spike=0.70),
            SignalRow(ticker="BBB", date=date(2026, 4, 21), momentum=0.69, volume_spike=0.69),
            SignalRow(ticker="CCC", date=date(2026, 4, 21), momentum=0.95, volume_spike=0.95),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 4, 21), ticker="AAA", company_name="AAA", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=4, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Nötr", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=100_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 4, 21), ticker="BBB", company_name="BBB", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=4, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Güçlü Al", technical_daily="Güçlü Al", technical_weekly="Al", technical_monthly="Nötr", avg_volume_3m=500_000, market_cap=12_000_000_000, beta=0.9, revenue=2_000_000_000, pe_ratio=12),
            MarketSnapshot(date=date(2026, 4, 21), ticker="CCC", company_name="CCC", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=4, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Nötr", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=100_000_000, pe_ratio=15),
        ]
        prices = [PriceBar(ticker=item.ticker, date=date(2026, 4, 21), open_price=9.5, close_price=10, volume=1_000_000) for item in snapshots]

        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=signals),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
            patch("stock_expert.services.passes_risk_filter", return_value=True),
        ):
            picks = generate_picks(self.settings, date(2026, 4, 21), dry_run=True)

        order = [pick.ticker for pick in picks[:3]]
        self.assertEqual(order[0], "CCC")
        self.assertLess(order.index("BBB"), order.index("AAA"))

    def test_bucketed_pick_selection_is_available_for_comparison(self) -> None:
        signals = [
            SignalRow(ticker="CORE1", date=date(2026, 4, 21), momentum=0.95, volume_spike=0.95, liquidity=1.0),
            SignalRow(ticker="CORE2", date=date(2026, 4, 21), momentum=0.93, volume_spike=0.94, liquidity=1.0),
            SignalRow(ticker="BREAK1", date=date(2026, 4, 21), momentum=0.9, volume_spike=0.65, liquidity=1.0),
            SignalRow(ticker="BREAK2", date=date(2026, 4, 21), momentum=0.88, volume_spike=0.62, liquidity=1.0),
            SignalRow(ticker="RECOV", date=date(2026, 4, 21), momentum=0.76, volume_spike=0.55, liquidity=1.0),
            SignalRow(ticker="FILL", date=date(2026, 4, 21), momentum=0.75, volume_spike=0.95, liquidity=1.0),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 4, 21), ticker="CORE1", company_name="CORE1", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=3, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Nötr", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 4, 21), ticker="CORE2", company_name="CORE2", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=2, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Nötr", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 4, 21), ticker="BREAK1", company_name="BREAK1", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=10, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Güçlü Al", technical_daily="Güçlü Al", technical_weekly="Güçlü Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 4, 21), ticker="BREAK2", company_name="BREAK2", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=9, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Güçlü Al", technical_daily="Güçlü Al", technical_weekly="Güçlü Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 4, 21), ticker="RECOV", company_name="RECOV", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=8, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Al", technical_daily="Al", technical_weekly="Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 4, 21), ticker="FILL", company_name="FILL", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=1, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Nötr", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
        ]
        prices = [PriceBar(ticker=item.ticker, date=date(2026, 4, 21), open_price=9.5, close_price=10, volume=1_000_000) for item in snapshots]

        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=signals),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
            patch("stock_expert.services.passes_risk_filter", return_value=True),
        ):
            picks = generate_bucketed_picks(self.settings, date(2026, 4, 21))

        self.assertEqual([pick.selection_bucket for pick in picks], ["core_momentum", "core_momentum", "breakout_technical", "breakout_technical", "coverage_recovery"])
        self.assertIn("BREAK1", [pick.ticker for pick in picks])
        self.assertIn("RECOV", [pick.ticker for pick in picks])

    def test_default_pick_selection_uses_score_ranked(self) -> None:
        signals = [
            SignalRow(ticker="AAA", date=date(2026, 4, 21), momentum=0.95, volume_spike=0.95, liquidity=1.0),
            SignalRow(ticker="BBB", date=date(2026, 4, 21), momentum=0.9, volume_spike=0.65, liquidity=1.0),
            SignalRow(ticker="CCC", date=date(2026, 4, 21), momentum=0.76, volume_spike=0.55, liquidity=1.0),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 4, 21), ticker=item.ticker, company_name=item.ticker, last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=1, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Güçlü Al", technical_daily="Güçlü Al", technical_weekly="Güçlü Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15)
            for item in signals
        ]
        prices = [PriceBar(ticker=item.ticker, date=date(2026, 4, 21), open_price=9.5, close_price=10, volume=1_000_000) for item in snapshots]

        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=signals),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
            patch("stock_expert.services.passes_risk_filter", return_value=True),
        ):
            picks = generate_picks(self.settings, date(2026, 4, 21), dry_run=True)

        self.assertEqual([pick.selection_bucket for pick in picks], ["score_ranked", "score_ranked", "score_ranked"])

    def test_weak_market_breadth_reduces_default_pick_count(self) -> None:
        signals = [
            SignalRow(ticker=f"AAA{i}", date=date(2026, 4, 21), momentum=0.9, volume_spike=0.9, liquidity=1.0)
            for i in range(6)
        ]
        prices = [
            PriceBar(ticker=item.ticker, date=date(2026, 4, 21), open_price=10.0, close_price=9.0 if i < 5 else 11.0, volume=1_000_000)
            for i, item in enumerate(signals)
        ]
        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=signals),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=[]),
            patch("stock_expert.services.passes_risk_filter", return_value=True),
        ):
            picks = generate_picks(self.settings, date(2026, 4, 21), dry_run=True)

        self.assertEqual(len(picks), 2)

    def test_weak_snapshot_context_can_demote_close_candidate(self) -> None:
        signals = [
            SignalRow(ticker="AAA", date=date(2026, 4, 21), momentum=0.80, volume_spike=0.80),
            SignalRow(ticker="BBB", date=date(2026, 4, 21), momentum=0.79, volume_spike=0.79),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 4, 21), ticker="AAA", company_name="AAA", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=2, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Sat", technical_daily="Güçlü Sat", technical_weekly="Sat", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=0, pe_ratio=-5),
            MarketSnapshot(date=date(2026, 4, 21), ticker="BBB", company_name="BBB", last_price=10, high_price=10.5, low_price=9.8, daily_change_pct=2, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Nötr", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
        ]
        prices = [PriceBar(ticker=item.ticker, date=date(2026, 4, 21), open_price=9.5, close_price=10, volume=1_000_000) for item in snapshots]

        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=signals),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 4, 21), momentum_weight=0.6, volume_weight=0.4)),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
            patch("stock_expert.services.passes_risk_filter", return_value=True),
        ):
            picks = generate_picks(self.settings, date(2026, 4, 21), dry_run=True)

        self.assertEqual([pick.ticker for pick in picks[:2]], ["BBB", "AAA"])
        self.assertGreater(picks[1].setup_penalty, 0.08)

    def test_shock_mode_demotes_bearish_intraday_candidate(self) -> None:
        signals = [
            SignalRow(ticker="WEAK", date=date(2026, 5, 21), momentum=0.95, volume_spike=0.95, liquidity=1.0),
            SignalRow(ticker="CALM", date=date(2026, 5, 21), momentum=0.9, volume_spike=0.9, liquidity=1.0),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 5, 21), ticker="WEAK", company_name="WEAK", last_price=10, high_price=11, low_price=9, daily_change_pct=-5.5, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Sat", technical_daily="Al", technical_weekly="Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
            MarketSnapshot(date=date(2026, 5, 21), ticker="CALM", company_name="CALM", last_price=10, high_price=11, low_price=9, daily_change_pct=1, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Nötr", technical_daily="Al", technical_weekly="Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=15),
        ]
        prices = [PriceBar(ticker=item.ticker, date=date(2026, 5, 21), open_price=9.5, close_price=10, volume=1_000_000) for item in snapshots]

        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.build_signals", return_value=signals),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_latest_weights", return_value=Weights(date=date(2026, 5, 21), momentum_weight=0.6, volume_weight=0.4)),
            patch("stock_expert.services.get_prices_for_date", return_value=prices),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
            patch("stock_expert.services.passes_risk_filter", return_value=True),
        ):
            picks = generate_picks(self.settings, date(2026, 5, 21), dry_run=True)

        self.assertEqual([pick.ticker for pick in picks[:2]], ["CALM", "WEAK"])

    def test_daily_summary_signal_ready_section_is_short(self) -> None:
        bars = [
            PriceBar(ticker="AAA", date=date(2026, 4, 21), open_price=9.0, close_price=10.0, volume=1_000_000),
            PriceBar(ticker="BBB", date=date(2026, 4, 21), open_price=8.0, close_price=9.0, volume=1_000_000),
        ]
        snapshots = [
            MarketSnapshot(date=date(2026, 4, 21), ticker="AAA", company_name="AAA", last_price=10, high_price=10.5, low_price=9.5, daily_change_pct=5, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Güçlü Al", technical_daily="Güçlü Al", technical_weekly="Al", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=12),
            MarketSnapshot(date=date(2026, 4, 21), ticker="BBB", company_name="BBB", last_price=9, high_price=9.2, low_price=8.8, daily_change_pct=4, volume=1_000_000, weekly_perf_pct=1, monthly_perf_pct=1, ytd_perf_pct=1, yearly_perf_pct=1, technical_hourly="Al", technical_daily="Al", technical_weekly="Nötr", technical_monthly="Nötr", avg_volume_3m=1_000_000, market_cap=1_000_000_000, beta=1.0, revenue=1_000_000_000, pe_ratio=12),
        ]
        picks = [
            PickRow(date=date(2026, 4, 21), ticker="AAA", score=1.0, momentum=0.8, volume=0.8, risk="high", technical=0.06, quality=0.01, fundamental=0.01),
            PickRow(date=date(2026, 4, 21), ticker="BBB", score=0.9, momentum=0.7, volume=0.7, risk="medium", technical=0.03, quality=0.01, fundamental=0.0),
        ]
        with (
            patch("stock_expert.services.init_db"),
            patch("stock_expert.services.get_prices_for_date", return_value=bars),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=snapshots),
            patch("stock_expert.services.generate_picks", return_value=picks),
        ):
            output = daily_summary(self.settings, date(2026, 4, 21))

        self.assertIn("Signal-Ready Leaders:", output)
        self.assertLessEqual(output.count("Adj"), 3)


if __name__ == "__main__":
    unittest.main()
