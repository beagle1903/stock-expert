from __future__ import annotations

import csv
import json
import shutil
import unittest
import uuid
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.daily_csv import (
    DailyCsvError,
    _load_ticker_map,
    _normalize_key,
    _parse_number,
    _resolve_ticker,
    _validate_live_ticker_coverage,
    import_daily_csv_command,
    import_daily_csv_folder_command,
)
from stock_expert.database import (
    create_snapshot_run,
    get_latest_snapshot_id,
    get_market_snapshots_for_date,
    init_db,
    upsert_market_snapshots,
)
from stock_expert.models import MarketSnapshot


class DailyCsvImportTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"daily_csv_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def _write_csv(self, name: str, headers: list[str], row: list[str]) -> None:
        path = self.settings.data_dir / name
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerow(row)

    def _write_csv_rows(self, name: str, headers: list[str], rows: list[list[str]]) -> None:
        path = self.settings.data_dir / name
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    def _write_ticker_map(self) -> None:
        self._write_csv(
            "ticker_map.csv",
            ["company_key", "ticker", "company_name", "matched_name", "match_type"],
            ["ADEL", "ADEL", "Adel", "Adel", "test"],
        )

    def _write_minimal_csv_set(self, revenue: str, pe_ratio: str) -> None:
        self._write_ticker_map()
        self._write_csv(
            "fiyat.csv",
            ["İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
            ["Adel", "46,10", "47,78", "44,60", "2,60", "5,98%", "11,48M", "18:09:44"],
        )
        self._write_csv(
            "performans.csv",
            ["İsim", "Günlük", "Haftalık", " 1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
            ["Adel", "5,98", "7,21", "36,39", "39,70", "20,37", "347,60"],
        )
        self._write_csv(
            "teknik.csv",
            ["İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
            ["Adel", "Güçlü Al", "Al", "Nötr", "Güçlü Al"],
        )
        self._write_csv(
            "temel.csv",
            ["İsim", "Ortalama Hacim (3Ay)", "Piyasa değeri", "Gelir", "Fiyat / Kazanç Oranı", "Beta"],
            ["Adel", "4,82M", "12,02Mlr", revenue, pe_ratio, "-0,59"],
        )

    def test_imports_revenue_and_pe_ratio(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 1)
        self.assertEqual(payload["price_basis"], "previous_close_to_last_from_daily_change_pct")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].revenue, 2_100_000_000.0)
        self.assertEqual(snapshots[0].pe_ratio, 12.77)

    def test_imports_english_decimal_format_without_scaling_values(self) -> None:
        self._write_ticker_map()
        self._write_csv(
            "fiyat.csv",
            ["İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
            ["Adel", "32.60", "33.70", "31.78", "+0.02", "+0.06%", "5.76M", "10:59:54"],
        )
        self._write_csv(
            "performans.csv",
            ["İsim", "Günlük", "Haftalık", " 1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
            ["Adel", "+0.06", "1.25", "2.50", "3.75", "4.25", "5.50"],
        )
        self._write_csv(
            "teknik.csv",
            ["İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
            ["Adel", "Strong Buy", "Buy", "Neutral", "Buy"],
        )
        self._write_csv(
            "temel.csv",
            ["İsim", "Ortalama Hacim (3Ay)", "Piyasa değeri", "Gelir", "Fiyat / Kazanç Oranı", "Beta"],
            ["Adel", "4.82M", "12.02B", "2.10B", "12.77", "-0.59"],
        )

        payload = json.loads(import_daily_csv_command(self.settings, "2026-08-18"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 8, 18))

        self.assertEqual(payload["decimal_separator"], ".")
        self.assertEqual(payload["rows_read"], 1)
        self.assertEqual(snapshots[0].last_price, 32.6)
        self.assertEqual(snapshots[0].daily_change_pct, 0.06)
        self.assertEqual(snapshots[0].volume, 5_760_000)
        self.assertEqual(snapshots[0].market_cap, 12_020_000_000)

    def test_number_parser_handles_locale_grouping(self) -> None:
        self.assertEqual(_parse_number("1.679,00", decimal_separator=","), 1679.0)
        self.assertEqual(_parse_number("1,679.00", decimal_separator="."), 1679.0)
        self.assertEqual(_parse_number("180.20", decimal_separator="."), 180.2)

    def test_ticker_map_loads_safe_name_and_symbol_aliases(self) -> None:
        self._write_csv_rows(
            "ticker_map.csv",
            ["company_key", "ticker", "company_name", "matched_name", "match_type"],
            [
                ["AYDEMENERJI", "AYDEM", "Aydem Enerji", "Aydem Yenilenebilir Enerji A.S.", "token_subset"],
                ["CEMZEYTIN", "CEMZY", "Cem Zeytin", "Cem Zeytin Anonim Sirketi", "prefix"],
                ["DEVAHOLDINGAS", "DEVA", "Deva Holding A.Ş.", "Deva Holding A.S.", "exact_key"],
                ["ORGEENERJIELEKTRIK", "ORGE", "Orge Enerji Elektrik", "Orge Enerji Elektrik", "prefix"],
            ],
        )

        ticker_map = _load_ticker_map(self.settings.data_dir / "ticker_map.csv")

        self.assertEqual(_resolve_ticker(ticker_map, "Aydem Yenilenebilir Enerji AS"), "AYDEM")
        self.assertEqual(_resolve_ticker(ticker_map, "Cem Zeytin AS"), "CEMZY")
        self.assertEqual(_resolve_ticker(ticker_map, "Deva Holding"), "DEVA")
        self.assertEqual(_resolve_ticker(ticker_map, "Orge"), "ORGE")

    def test_large_live_import_rejects_low_ticker_coverage(self) -> None:
        with self.assertRaisesRegex(DailyCsvError, "ticker coverage is too low"):
            _validate_live_ticker_coverage(source_rows=653, eligible_rows=634, distinct_tickers=402)

        self.assertAlmostEqual(
            _validate_live_ticker_coverage(source_rows=653, eligible_rows=634, distinct_tickers=509),
            509 / 634,
        )

    def test_malformed_fundamentals_fall_back_to_neutral(self) -> None:
        self._write_minimal_csv_set("", "N/A")
        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 1)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].revenue, 0.0)
        self.assertEqual(snapshots[0].pe_ratio, 0.0)

    def test_enriched_fields_round_trip_through_sqlite(self) -> None:
        init_db(self.settings)
        snapshot_id = create_snapshot_run(self.settings, date(2026, 4, 21), "test", "data")
        snapshot = MarketSnapshot(
            date=date(2026, 4, 21),
            ticker="ADEL",
            company_name="Adel",
            last_price=46.1,
            high_price=47.78,
            low_price=44.6,
            daily_change_pct=5.98,
            volume=11_480_000,
            weekly_perf_pct=7.21,
            monthly_perf_pct=36.39,
            ytd_perf_pct=39.7,
            yearly_perf_pct=20.37,
            technical_hourly="Güçlü Al",
            technical_daily="Al",
            technical_weekly="Nötr",
            technical_monthly="Güçlü Al",
            avg_volume_3m=4_820_000,
            market_cap=12_020_000_000,
            beta=-0.59,
            revenue=2_100_000_000,
            pe_ratio=12.77,
        )
        upsert_market_snapshots(self.settings, [snapshot], snapshot_id=snapshot_id)
        loaded = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].revenue, 2_100_000_000)
        self.assertEqual(loaded[0].pe_ratio, 12.77)
        self.assertEqual(loaded[0].technical_daily, "Al")

    def test_unmapped_rows_are_skipped(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        (self.settings.data_dir / "ticker_map.csv").unlink()

        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))

        self.assertEqual(payload["rows_read"], 0)
        self.assertEqual(payload["skipped_unmapped_count"], 1)

    def test_malformed_required_price_row_is_skipped(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        path = self.settings.data_dir / "fiyat.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        rows[1][1] = "bad-price"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)

        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))

        self.assertEqual(payload["rows_read"], 0)
        self.assertEqual(payload["skipped_malformed_count"], 1)

    def test_non_finite_required_price_row_is_skipped(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        path = self.settings.data_dir / "fiyat.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        rows[1][1] = "NaN"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle).writerows(rows)

        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))

        self.assertEqual(payload["rows_read"], 0)
        self.assertEqual(payload["skipped_malformed_count"], 1)

    def test_failed_snapshot_write_rolls_back_new_run(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        previous_id = create_snapshot_run(self.settings, date(2026, 4, 21), "test", "previous")

        with patch("stock_expert.database._upsert_prices_conn", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                import_daily_csv_command(self.settings, "2026-04-21")

        self.assertEqual(get_latest_snapshot_id(self.settings, date(2026, 4, 21)), previous_id)

    def test_folder_import_uses_holiday_aware_previous_session(self) -> None:
        with patch(
            "stock_expert.daily_csv.import_daily_csv_command",
            return_value=json.dumps({"snapshot_id": 1}),
        ) as import_command:
            payload = json.loads(import_daily_csv_folder_command(self.settings, "data/20260601"))

        import_command.assert_called_once_with(
            settings=self.settings,
            snapshot_date="2026-05-26",
            data_dir="data/20260601",
        )
        self.assertEqual(payload["target_trade_date"], "2026-06-01")

    def test_market_snapshot_table_migrates_new_columns(self) -> None:
        import sqlite3

        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE market_snapshots (
                    snapshot_id INTEGER NOT NULL DEFAULT 0,
                    date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    last_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    daily_change_pct REAL NOT NULL,
                    volume REAL NOT NULL,
                    weekly_perf_pct REAL NOT NULL,
                    monthly_perf_pct REAL NOT NULL,
                    ytd_perf_pct REAL NOT NULL,
                    yearly_perf_pct REAL NOT NULL,
                    technical_hourly TEXT NOT NULL,
                    technical_daily TEXT NOT NULL,
                    technical_weekly TEXT NOT NULL,
                    technical_monthly TEXT NOT NULL,
                    avg_volume_3m REAL NOT NULL,
                    market_cap REAL NOT NULL,
                    beta REAL NOT NULL,
                    PRIMARY KEY (snapshot_id, ticker)
                )
                """
            )

        init_db(self.settings)

        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(market_snapshots)")}

        self.assertIn("revenue", columns)
        self.assertIn("pe_ratio", columns)


if __name__ == "__main__":
    unittest.main()
