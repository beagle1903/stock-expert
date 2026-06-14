from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_expert.models import MarketSnapshot, PriceBar
from stock_expert.signals import (
    classify_risk,
    compute_fundamental_adjustment,
    compute_liquidity,
    compute_ma_trend,
    compute_medium_momentum,
    compute_momentum,
    compute_setup_penalty,
    compute_short_momentum,
    compute_volume_spike,
)


class SignalCalculationTests(unittest.TestCase):
    def _bars(
        self,
        closes: list[float],
        volumes: list[float] | None = None,
    ) -> list[PriceBar]:
        volumes = volumes or [100.0] * len(closes)
        start = date(2026, 4, 1)
        return [
            PriceBar(
                ticker="AAA",
                date=start + timedelta(days=index),
                open_price=close_price,
                close_price=close_price,
                volume=volumes[index],
            )
            for index, close_price in enumerate(closes)
        ]

    def _snapshot(self, **overrides: object) -> MarketSnapshot:
        values = {
            "date": date(2026, 4, 21),
            "ticker": "AAA",
            "company_name": "AAA",
            "last_price": 10.0,
            "high_price": 11.0,
            "low_price": 9.0,
            "daily_change_pct": 1.0,
            "volume": 1000.0,
            "weekly_perf_pct": 1.0,
            "monthly_perf_pct": 1.0,
            "ytd_perf_pct": 1.0,
            "yearly_perf_pct": 1.0,
            "technical_hourly": "Nötr",
            "technical_daily": "Nötr",
            "technical_weekly": "Nötr",
            "technical_monthly": "Nötr",
            "avg_volume_3m": 1000.0,
            "market_cap": 1_000_000_000.0,
            "beta": 1.0,
            "revenue": 1_000_000_000.0,
            "pe_ratio": 15.0,
        }
        values.update(overrides)
        return MarketSnapshot(**values)

    def test_momentum_windows_and_ma_trend_cover_short_zero_and_rising_history(self) -> None:
        self.assertEqual(compute_short_momentum(self._bars([10.0, 11.0])), 0.0)
        self.assertEqual(compute_medium_momentum(self._bars([0.0] * 6)), 0.0)

        rising = self._bars([10.0, 10.5, 11.0, 11.5, 12.0, 13.0])
        self.assertGreater(compute_short_momentum(rising), 0.5)
        self.assertGreater(compute_medium_momentum(rising), 0.5)
        self.assertEqual(compute_ma_trend(rising), 1.0)
        self.assertGreater(compute_momentum(rising), 0.5)

    def test_volume_liquidity_and_risk_cover_boundaries(self) -> None:
        self.assertEqual(compute_volume_spike(self._bars([10.0] * 4)), 0.0)
        self.assertEqual(compute_volume_spike(self._bars([10.0] * 5, [0.0] * 5)), 0.0)
        self.assertEqual(compute_volume_spike(self._bars([10.0] * 5, [100.0, 100.0, 100.0, 100.0, 300.0])), 1.0)
        self.assertEqual(compute_liquidity([], 100.0), 0.0)
        self.assertEqual(compute_liquidity(self._bars([10.0]), 0.0), 0.0)
        self.assertEqual(compute_liquidity(self._bars([10.0], [50.0]), 100.0), 1.0)
        self.assertEqual(classify_risk(0.1, 0.1), "low")
        self.assertEqual(classify_risk(0.6, 0.1), "medium")
        self.assertEqual(classify_risk(0.9, 0.1), "high")

    def test_fundamental_and_setup_edges_are_bounded(self) -> None:
        self.assertGreater(compute_fundamental_adjustment(self._snapshot(pe_ratio=30.0)), 0.0)
        self.assertLess(compute_fundamental_adjustment(self._snapshot(pe_ratio=100.0)), 0.02)

        price = self._bars([10.0], [9000.0])[0]
        weak = self._snapshot(
            market_cap=0.0,
            avg_volume_3m=1000.0,
            pe_ratio=100.0,
            weekly_perf_pct=25.0,
            monthly_perf_pct=35.0,
            daily_change_pct=9.0,
        )
        quiet = self._snapshot(avg_volume_3m=10_000.0)
        self.assertEqual(compute_setup_penalty(weak, price), 0.11)
        self.assertEqual(compute_setup_penalty(quiet, self._bars([10.0], [1000.0])[0]), 0.015)


if __name__ == "__main__":
    unittest.main()
