from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from stock_expert import services
from stock_expert.config import Settings
from stock_expert.models import PriceBar, SignalRow
from stock_expert.signal_window import (
    SIGNAL_WINDOW_BARS,
    SIGNAL_WINDOW_COMPONENTS,
    assess_signal_window,
    signal_window_warning,
)
from stock_expert.signals import (
    compute_ma_trend,
    compute_medium_momentum,
    compute_short_momentum,
    compute_volume_spike,
)


def _days(*values: str) -> list[date]:
    return [date.fromisoformat(value) for value in values]


def _bars(count: int) -> list[PriceBar]:
    return [
        PriceBar(
            ticker="AAA",
            date=date(2026, 11, 2 + index),
            open_price=10.0 + index,
            close_price=10.5 + index,
            volume=1_000.0 * (index + 1),
        )
        for index in range(count)
    ]


class SignalWindowAssessmentTests(unittest.TestCase):
    def test_contiguous_window_reads_consecutive_sessions(self) -> None:
        coverage = assess_signal_window(
            date(2026, 11, 18),
            _days("2026-11-18", "2026-11-17", "2026-11-16", "2026-11-13", "2026-11-12", "2026-11-11", "2026-11-10"),
        )

        assert coverage is not None
        self.assertEqual(coverage.status, "contiguous")
        self.assertEqual(coverage.window_bars, 6)
        self.assertEqual(coverage.window_start, date(2026, 11, 11))
        self.assertEqual(coverage.window_end, date(2026, 11, 18))
        self.assertEqual(coverage.missing_sessions, ())
        self.assertEqual(coverage.non_session_dates, ())
        self.assertEqual(coverage.affected_components, ())
        self.assertIsNone(signal_window_warning(coverage))

    def test_one_missing_session_affects_every_component(self) -> None:
        # Live DB has no 2026-11-16 snapshot; the 2026-11-18 window jumps it.
        coverage = assess_signal_window(
            date(2026, 11, 18),
            _days("2026-11-18", "2026-11-17", "2026-11-13", "2026-11-12", "2026-11-11", "2026-11-10"),
        )

        assert coverage is not None
        self.assertEqual(coverage.status, "gap")
        self.assertEqual(coverage.window_start, date(2026, 11, 10))
        self.assertEqual(coverage.missing_sessions, (date(2026, 11, 16),))
        self.assertEqual(coverage.non_session_dates, ())
        self.assertEqual(coverage.affected_components, ("momentum", "volume", "fade_then_rechase"))
        self.assertEqual(
            coverage.to_payload(),
            {
                "status": "gap",
                "window_bars": 6,
                "window_start": "2026-11-10",
                "window_end": "2026-11-18",
                "missing_sessions": ["2026-11-16"],
                "non_session_dates": [],
                "affected_components": ["momentum", "volume", "fade_then_rechase"],
            },
        )

    def test_multi_session_gap_lists_sessions_and_skips_the_holiday(self) -> None:
        coverage = assess_signal_window(
            date(2026, 10, 30),
            _days("2026-10-30", "2026-10-15", "2026-10-14", "2026-10-13", "2026-10-12", "2026-10-09"),
        )

        assert coverage is not None
        self.assertEqual(coverage.status, "gap")
        self.assertEqual(
            coverage.missing_sessions,
            tuple(
                _days(
                    "2026-10-16",
                    "2026-10-19",
                    "2026-10-20",
                    "2026-10-21",
                    "2026-10-22",
                    "2026-10-23",
                    "2026-10-26",
                    "2026-10-27",
                    # 2026-10-28 is the Republic Day eve half day: still a session.
                    "2026-10-28",
                )
            ),
        )
        # 2026-10-29 is Republic Day, a closure, never a missing session.
        self.assertNotIn(date(2026, 10, 29), coverage.missing_sessions)
        self.assertEqual(coverage.affected_components, ("momentum", "volume", "fade_then_rechase"))

    def test_old_gap_affects_only_the_longest_component(self) -> None:
        # 2026-11-11 is missing behind the 5 newest dates, so only the
        # 6-bar momentum window reaches across it.
        coverage = assess_signal_window(
            date(2026, 11, 18),
            _days("2026-11-18", "2026-11-17", "2026-11-16", "2026-11-13", "2026-11-12", "2026-11-10"),
        )

        assert coverage is not None
        self.assertEqual(coverage.status, "gap")
        self.assertEqual(coverage.missing_sessions, (date(2026, 11, 11),))
        self.assertEqual(coverage.affected_components, ("momentum",))

    def test_non_session_snapshot_date_is_a_gap(self) -> None:
        # Snapshot 176 was stored under Saturday 2026-11-07.
        coverage = assess_signal_window(
            date(2026, 11, 10),
            _days("2026-11-10", "2026-11-09", "2026-11-07", "2026-11-06", "2026-11-05", "2026-11-04"),
        )

        assert coverage is not None
        self.assertEqual(coverage.status, "gap")
        self.assertEqual(coverage.missing_sessions, ())
        self.assertEqual(coverage.non_session_dates, (date(2026, 11, 7),))
        self.assertEqual(coverage.affected_components, ("momentum", "volume", "fade_then_rechase"))
        warning = signal_window_warning(coverage)
        assert warning is not None
        self.assertIn("non-session snapshot date(s) 2026-11-07", warning)
        self.assertNotIn("missing trading session", warning)

    def test_non_session_date_only_in_momentum_window(self) -> None:
        coverage = assess_signal_window(
            date(2026, 11, 13),
            _days("2026-11-13", "2026-11-12", "2026-11-11", "2026-11-10", "2026-11-09", "2026-11-07"),
        )

        assert coverage is not None
        self.assertEqual(coverage.non_session_dates, (date(2026, 11, 7),))
        self.assertEqual(coverage.missing_sessions, ())
        self.assertEqual(coverage.affected_components, ("momentum",))

    def test_short_history_uses_every_available_date(self) -> None:
        contiguous = assess_signal_window(date(2026, 11, 18), _days("2026-11-18", "2026-11-17", "2026-11-16"))
        gapped = assess_signal_window(date(2026, 11, 18), _days("2026-11-18", "2026-11-13"))

        assert contiguous is not None and gapped is not None
        self.assertEqual(contiguous.status, "contiguous")
        self.assertEqual(contiguous.window_bars, 3)
        self.assertEqual(contiguous.window_start, date(2026, 11, 16))
        self.assertEqual(gapped.status, "gap")
        self.assertEqual(gapped.window_bars, 2)
        self.assertEqual(gapped.missing_sessions, _days_tuple("2026-11-16", "2026-11-17"))
        self.assertEqual(gapped.affected_components, ("momentum", "volume", "fade_then_rechase"))

    def test_no_coverage_without_a_signal_date_snapshot(self) -> None:
        self.assertIsNone(assess_signal_window(date(2026, 11, 18), []))
        self.assertIsNone(
            assess_signal_window(date(2026, 11, 18), _days("2026-11-17", "2026-11-16", "2026-11-13"))
        )

    def test_dates_after_the_signal_date_are_ignored(self) -> None:
        coverage = assess_signal_window(
            date(2026, 11, 17),
            _days("2026-11-18", "2026-11-17", "2026-11-16", "2026-11-13", "2026-11-12", "2026-11-11", "2026-11-10"),
        )

        assert coverage is not None
        self.assertEqual(coverage.window_end, date(2026, 11, 17))
        self.assertEqual(coverage.window_start, date(2026, 11, 10))
        self.assertEqual(coverage.status, "contiguous")

    def test_warning_is_one_ascii_sentence(self) -> None:
        coverage = assess_signal_window(
            date(2026, 11, 18),
            _days("2026-11-18", "2026-11-17", "2026-11-13", "2026-11-12", "2026-11-11", "2026-11-10"),
        )

        warning = signal_window_warning(coverage)

        self.assertEqual(
            warning,
            "Signal window 2026-11-10 to 2026-11-18 spans missing trading session(s) 2026-11-16; "
            "momentum, volume, fade_then_rechase read non-contiguous bars. Scores are unchanged.",
        )
        assert warning is not None
        warning.encode("ascii")
        self.assertIsNone(signal_window_warning(None))

    def test_warning_names_missing_sessions_and_non_session_dates(self) -> None:
        coverage = assess_signal_window(
            date(2026, 11, 12),
            _days("2026-11-12", "2026-11-11", "2026-11-10", "2026-11-07", "2026-11-06", "2026-11-02"),
        )

        warning = signal_window_warning(coverage)

        assert warning is not None
        warning.encode("ascii")
        self.assertIn("spans missing trading session(s) 2026-11-03, 2026-11-04, 2026-11-05, 2026-11-09", warning)
        self.assertIn("and includes non-session snapshot date(s) 2026-11-07", warning)


def _days_tuple(*values: str) -> tuple[date, ...]:
    return tuple(_days(*values))


class SignalWindowComponentPinTests(unittest.TestCase):
    """SIGNAL_WINDOW_COMPONENTS must equal the real component lookbacks."""

    def test_window_is_the_longest_component(self) -> None:
        self.assertEqual(SIGNAL_WINDOW_BARS, max(SIGNAL_WINDOW_COMPONENTS.values()))
        self.assertEqual(set(SIGNAL_WINDOW_COMPONENTS), {"momentum", "volume", "fade_then_rechase"})

    def test_momentum_lookback(self) -> None:
        bars = SIGNAL_WINDOW_COMPONENTS["momentum"]
        self.assertEqual(compute_medium_momentum(_bars(bars - 1)), 0.0)
        self.assertNotEqual(compute_medium_momentum(_bars(bars)), 0.0)
        # The other momentum parts read no further back than medium momentum.
        self.assertNotEqual(compute_short_momentum(_bars(bars)), 0.0)
        self.assertNotEqual(compute_ma_trend(_bars(bars)), 0.0)
        self.assertEqual(compute_short_momentum(_bars(3)), 0.0)
        self.assertNotEqual(compute_short_momentum(_bars(4)), 0.0)
        self.assertEqual(compute_ma_trend(_bars(4)), 0.0)
        self.assertNotEqual(compute_ma_trend(_bars(5)), 0.0)

    def test_volume_lookback(self) -> None:
        bars = SIGNAL_WINDOW_COMPONENTS["volume"]
        self.assertEqual(compute_volume_spike(_bars(bars - 1)), 0.0)
        self.assertNotEqual(compute_volume_spike(_bars(bars)), 0.0)

    def test_fade_then_rechase_fetch(self) -> None:
        as_of = date(2026, 11, 18)
        signal = SignalRow(ticker="AAA", date=as_of, momentum=0.9, volume_spike=0.9)
        settings = Settings(base_dir=".", data_dir="data", db_path="data/unused.db")
        with (
            patch("stock_expert.services.build_signals", return_value=[signal]),
            patch("stock_expert.services.get_latest_snapshot_id", return_value=1),
            patch("stock_expert.services.get_strategy_pilot_state", return_value=None),
            patch("stock_expert.services.get_weights_as_of", return_value=None),
            patch("stock_expert.services.get_prices_for_date", return_value=[]),
            patch("stock_expert.services.get_market_snapshots_for_date", return_value=[]),
            patch("stock_expert.services.passes_risk_filter", return_value=False),
            patch("stock_expert.services.get_recent_price_history", return_value=[]) as history,
        ):
            services._compute_ranked_candidate_rows(settings, as_of)

        history.assert_called_once_with(settings, as_of, bars=SIGNAL_WINDOW_COMPONENTS["fade_then_rechase"])


if __name__ == "__main__":
    unittest.main()
