from __future__ import annotations

import json
import shutil
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.database import (
    DAILY_CSV_SOURCE,
    LEGACY_SOURCE,
    OPERATIONAL_SNAPSHOT_SOURCES,
    YAHOO_OHLCV_SOURCE,
    connect,
    create_snapshot_run,
    get_latest_snapshot_id,
    get_pick_results,
    get_prices_between,
    get_prices_for_date,
    get_recent_price_history,
    get_top_movers,
    init_db,
    persist_yahoo_prices,
    replace_picks_for_date,
    upsert_prices,
)
from stock_expert.models import PickRow
from stock_expert.services import review_output
from stock_expert.trading_calendar import is_trading_session, previous_trading_session


NON_OPERATIONAL_LABELS = ("yahoo_history_browser", "manual_repair")


class OperationalSnapshotSourceTests(unittest.TestCase):
    """Only daily_csv and legacy runs may feed ranking, selection, or review."""

    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"opsrc_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.settings)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def _run(self, day: date, label: str, prices: dict[str, tuple[float, float]]) -> int:
        snapshot_id = create_snapshot_run(self.settings, day, label, f"test/{label}")
        upsert_prices(
            self.settings,
            [(snapshot_id, ticker, day, open_p, close_p, 1000.0) for ticker, (open_p, close_p) in prices.items()],
        )
        return snapshot_id

    def test_allow_list_is_daily_csv_and_legacy_only(self) -> None:
        self.assertEqual(OPERATIONAL_SNAPSHOT_SOURCES, (DAILY_CSV_SOURCE, LEGACY_SOURCE))
        self.assertNotIn(YAHOO_OHLCV_SOURCE, OPERATIONAL_SNAPSHOT_SOURCES)

    def test_latest_snapshot_id_ignores_non_operational_labels(self) -> None:
        for label in NON_OPERATIONAL_LABELS:
            with self.subTest(label=label):
                self._clear()
                only_day = date(2026, 4, 14)
                both_day = date(2026, 4, 15)
                self._run(only_day, label, {"AAA": (10.0, 11.0)})
                daily_id = self._run(both_day, DAILY_CSV_SOURCE, {"AAA": (10.0, 10.5)})
                foreign_id = self._run(both_day, label, {"AAA": (10.0, 99.0)})

                self.assertGreater(foreign_id, daily_id)
                self.assertIsNone(get_latest_snapshot_id(self.settings, only_day))
                self.assertEqual(get_latest_snapshot_id(self.settings, both_day), daily_id)

    def test_legacy_runs_remain_operational(self) -> None:
        day = date(2026, 4, 16)
        legacy_id = self._run(day, LEGACY_SOURCE, {"AAA": (10.0, 10.2)})
        self._run(day, "yahoo_history_browser", {"AAA": (10.0, 50.0)})

        self.assertEqual(get_latest_snapshot_id(self.settings, day), legacy_id)
        self.assertEqual([bar.close_price for bar in get_prices_for_date(self.settings, day)], [10.2])

    def test_yahoo_ohlcv_remains_excluded(self) -> None:
        day = date(2026, 4, 16)
        persist_yahoo_prices(self.settings, [("AAA", day, 10.0, 50.0, 1000.0)])

        self.assertIsNone(get_latest_snapshot_id(self.settings, day))
        self.assertEqual(get_prices_for_date(self.settings, day), [])

    def test_price_reads_ignore_non_operational_labels(self) -> None:
        for label in NON_OPERATIONAL_LABELS:
            with self.subTest(label=label):
                self._clear()
                only_day = date(2026, 4, 14)
                both_day = date(2026, 4, 15)
                self._run(only_day, label, {"ZZZ": (10.0, 30.0)})
                self._run(both_day, DAILY_CSV_SOURCE, {"AAA": (10.0, 10.5)})
                self._run(both_day, label, {"AAA": (10.0, 99.0), "ZZZ": (10.0, 30.0)})

                self.assertEqual(get_prices_for_date(self.settings, only_day), [])
                both_bars = get_prices_for_date(self.settings, both_day)
                self.assertEqual([(bar.ticker, bar.close_price) for bar in both_bars], [("AAA", 10.5)])

                between = get_prices_between(self.settings, only_day, both_day)
                self.assertEqual([(bar.ticker, bar.date, bar.close_price) for bar in between], [("AAA", both_day, 10.5)])

                movers = get_top_movers(self.settings, both_day, 2, limit=10)
                self.assertEqual([(row["ticker"], row["close_price"]) for row in movers], [("AAA", 10.5)])

    def test_recent_price_history_skips_non_operational_dates(self) -> None:
        for label in NON_OPERATIONAL_LABELS:
            with self.subTest(label=label):
                self._clear()
                first = date(2026, 4, 15)
                middle = date(2026, 4, 16)
                last = date(2026, 4, 17)
                only_foreign = date(2026, 4, 20)
                self._run(first, DAILY_CSV_SOURCE, {"AAA": (10.0, 10.1)})
                self._run(middle, label, {"AAA": (10.0, 77.0), "ZZZ": (5.0, 9.0)})
                self._run(last, DAILY_CSV_SOURCE, {"AAA": (10.1, 10.3)})
                self._run(only_foreign, label, {"AAA": (10.3, 88.0)})

                self.assertEqual(get_recent_price_history(self.settings, only_foreign, 2), [])

                history = get_recent_price_history(self.settings, last, 2)
                self.assertEqual(
                    [(bar.ticker, bar.date, bar.close_price) for bar in history],
                    [("AAA", first, 10.1), ("AAA", last, 10.3)],
                )

    def test_review_pricing_ignores_non_operational_review_snapshot(self) -> None:
        review_day = date(2026, 4, 21)
        signal_day = previous_trading_session(review_day)
        self.assertTrue(is_trading_session(review_day))
        self.assertTrue(is_trading_session(signal_day))

        signal_id = self._run(signal_day, DAILY_CSV_SOURCE, {"AAA": (10.0, 10.2)})
        pick = PickRow(date=signal_day, ticker="AAA", score=1.0, momentum=0.1, volume=0.1, risk="low")
        replace_picks_for_date(self.settings, [pick], signal_day, snapshot_id=signal_id)
        self._run(review_day, "yahoo_history_browser", {"AAA": (10.0, 12.0), "ZZZ": (10.0, 20.0)})

        self.assertEqual(get_pick_results(self.settings, signal_day, review_day), [])

        with (
            patch("stock_expert.services.ensure_base_state"),
            patch("stock_expert.services.generate_picks", return_value=[pick]),
            patch("stock_expert.services._candidate_rankings", return_value={}),
            patch("stock_expert.services.insert_weights") as insert_weights,
            patch("stock_expert.services.persist_review_bundle") as persist_review_bundle,
        ):
            payload = json.loads(review_output(self.settings, review_day, dry_run=True))

        insert_weights.assert_not_called()
        persist_review_bundle.assert_not_called()
        self.assertEqual(payload["performance"]["pick_count"], 0)
        self.assertEqual(payload["performance"]["avg_return"], 0.0)
        self.assertEqual(payload["reviewed_picks"], [])
        self.assertEqual(payload["missed_top_movers"], [])

    def _clear(self) -> None:
        with connect(self.settings) as conn:
            conn.execute("DELETE FROM picks")
            conn.execute("DELETE FROM stocks")
            conn.execute("DELETE FROM snapshot_runs")


if __name__ == "__main__":
    unittest.main()
