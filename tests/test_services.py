from __future__ import annotations

import json
import unittest
import uuid
from datetime import date
from pathlib import Path
import shutil
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.models import MarketSnapshot, PickRow, PriceBar, SignalRow, Weights
from stock_expert.services import daily_summary, generate_picks, next_weekday, picks_output, previous_weekday, review_output
from stock_expert.signals import (
    compute_fundamental_adjustment,
    compute_quality_adjustment,
    compute_technical_adjustment,
    score_signal,
)


class ServiceDateTests(unittest.TestCase):
    def test_next_weekday_skips_weekend(self) -> None:
        self.assertEqual(next_weekday(date(2026, 4, 24)), date(2026, 4, 27))

    def test_previous_weekday_skips_weekend(self) -> None:
        self.assertEqual(previous_weekday(date(2026, 4, 27)), date(2026, 4, 24))


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

    def test_no_chase_comparison_can_change_basket(self) -> None:
        from stock_expert.services import apply_same_day_chase_penalty

        base_score = 1.03
        penalized = apply_same_day_chase_penalty(self._settings_stub(), base_score, 12.0)
        self.assertLess(penalized, base_score)

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
            patch("stock_expert.services.get_review_run", return_value=None),
            patch("stock_expert.services.insert_weights") as insert_weights,
            patch("stock_expert.services.insert_review_run", return_value=7) as insert_review_run,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        insert_weights.assert_called_once()
        insert_review_run.assert_called_once()
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["review_run_id"], 7)

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
            patch("stock_expert.services.insert_weights") as insert_weights,
            patch("stock_expert.services.insert_review_run") as insert_review_run,
        ):
            payload = json.loads(review_output(self.settings, date(2026, 4, 21), dry_run=False))

        insert_weights.assert_not_called()
        insert_review_run.assert_not_called()
        self.assertEqual(payload["review_run_id"], 7)
        self.assertEqual(payload["adjustments"]["momentum_weight"], 0.63)

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
            ma_trend=0.6,
            liquidity=0.9,
            risk="medium",
        )
        with patch("stock_expert.services.generate_picks", return_value=[pick]):
            payload = json.loads(picks_output(self.settings, date(2026, 4, 21), dry_run=True))

        self.assertIn("adjustments", payload["picks"][0])
        self.assertEqual(payload["picks"][0]["adjustments"]["total_boost"], 0.06)


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
