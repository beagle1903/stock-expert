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
    get_latest_weights,
    get_pick_results,
    get_prices_between,
    get_prices_for_date,
    get_recent_price_history,
    get_review_run,
    get_top_movers,
    init_db,
    insert_review_run,
    insert_weights,
    replace_picks_for_date,
    upsert_prices,
    upsert_signals,
)
from stock_expert.models import PickRow, SignalRow, Weights


class PricePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"prices_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.settings)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def test_legacy_price_rows_initialize_once_and_create_one_snapshot_per_date(self) -> None:
        rows = [
            (f"AAA{index}", date(2026, 4, 20), 10.0, 11.0, 1000.0)
            for index in range(3)
        ] + [
            (f"BBB{index}", date(2026, 4, 21), 20.0, 21.0, 2000.0)
            for index in range(3)
        ]

        with patch("stock_expert.database.init_db", wraps=init_db) as initialize:
            upsert_prices(self.settings, rows)

        with connect(self.settings) as conn:
            snapshot_count = conn.execute("SELECT COUNT(*) FROM snapshot_runs").fetchone()[0]
            stock_count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]

        self.assertEqual(initialize.call_count, 1)
        self.assertEqual(snapshot_count, 2)
        self.assertEqual(stock_count, 6)

    def test_price_read_helpers_use_latest_snapshot_per_date(self) -> None:
        first_id = create_snapshot_run(self.settings, date(2026, 4, 20), "test", "first")
        latest_id = create_snapshot_run(self.settings, date(2026, 4, 20), "test", "latest")
        next_id = create_snapshot_run(self.settings, date(2026, 4, 21), "test", "next")
        upsert_prices(
            self.settings,
            [
                (first_id, "AAA", date(2026, 4, 20), 10.0, 10.5, 100.0),
                (latest_id, "AAA", date(2026, 4, 20), 10.0, 11.0, 200.0),
                (next_id, "AAA", date(2026, 4, 21), 11.0, 12.0, 300.0),
                (next_id, "BBB", date(2026, 4, 21), 10.0, 9.0, 400.0),
            ],
        )

        daily = get_prices_for_date(self.settings, date(2026, 4, 20))
        between = get_prices_between(self.settings, date(2026, 4, 20), date(2026, 4, 21))
        history = get_recent_price_history(self.settings, date(2026, 4, 21), bars=2)
        movers = get_top_movers(self.settings, date(2026, 4, 21), days=2, limit=2)

        self.assertEqual([(row.ticker, row.close_price) for row in daily], [("AAA", 11.0)])
        self.assertEqual(len(between), 3)
        self.assertEqual(len(history), 3)
        self.assertEqual(movers[0]["ticker"], "AAA")
        self.assertEqual(get_prices_for_date(self.settings, date(2026, 4, 19)), [])
        self.assertEqual(get_recent_price_history(self.settings, date(2026, 4, 22), bars=2), [])

    def test_signal_pick_weight_and_review_helpers_round_trip(self) -> None:
        signal_date = date(2026, 4, 20)
        review_date = date(2026, 4, 21)
        signal_snapshot = create_snapshot_run(self.settings, signal_date, "test", "signal")
        target_snapshot = create_snapshot_run(self.settings, review_date, "test", "target")
        upsert_prices(
            self.settings,
            [
                (signal_snapshot, "AAA", signal_date, 10.0, 11.0, 100.0),
                (target_snapshot, "AAA", review_date, 11.0, 12.0, 200.0),
            ],
        )
        upsert_signals(
            self.settings,
            [SignalRow(ticker="AAA", date=signal_date, momentum=0.8, volume_spike=0.7)],
            snapshot_id=signal_snapshot,
        )
        replace_picks_for_date(
            self.settings,
            [
                PickRow(
                    date=signal_date,
                    ticker="AAA",
                    score=0.9,
                    momentum=0.8,
                    volume=0.7,
                    risk="medium",
                )
            ],
            signal_date,
            snapshot_id=signal_snapshot,
        )
        weights = Weights(date=review_date, momentum_weight=0.65, volume_weight=0.35)
        insert_weights(self.settings, weights)

        results = get_pick_results(self.settings, signal_date, review_date)
        review_id = insert_review_run(
            self.settings,
            as_of=signal_date,
            review_date=review_date,
            avg_return=results[0]["close_price"] / results[0]["open_price"] - 1,
            win_rate=1.0,
            picks=results,
            weights=weights,
        )

        self.assertEqual(results[0]["ticker"], "AAA")
        self.assertEqual(get_latest_weights(self.settings), weights)
        self.assertEqual(get_review_run(self.settings, signal_date, review_date)["id"], review_id)
        self.assertEqual(get_pick_results(self.settings, date(2026, 4, 19), review_date), [])


if __name__ == "__main__":
    unittest.main()
