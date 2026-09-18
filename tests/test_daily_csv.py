from __future__ import annotations

import csv
import json
import shutil
import sqlite3
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

    def _with_optional_symbol(
        self,
        filename: str,
        headers: list[str],
        row: list[str],
        symbol_header: str | None,
        symbol_value: str | None,
        table_symbols: dict[str, str] | None,
    ) -> tuple[list[str], list[str]]:
        if not symbol_header:
            return headers, row
        value = "" if table_symbols is None and symbol_value is None else (table_symbols or {}).get(filename, symbol_value or "")
        return [headers[0], symbol_header, *headers[1:]], [row[0], value, *row[1:]]

    def _write_minimal_csv_set(
        self,
        revenue: str,
        pe_ratio: str,
        *,
        write_ticker_map: bool = True,
        symbol_header: str | None = None,
        symbol_value: str | None = None,
        table_symbols: dict[str, str] | None = None,
    ) -> None:
        if write_ticker_map:
            self._write_ticker_map()
        files = (
            (
                "fiyat.csv",
                ["İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
                ["Adel", "46,10", "47,78", "44,60", "2,60", "5,98%", "11,48M", "18:09:44"],
            ),
            (
                "performans.csv",
                ["İsim", "Günlük", "Haftalık", " 1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
                ["Adel", "5,98", "7,21", "36,39", "39,70", "20,37", "347,60"],
            ),
            (
                "teknik.csv",
                ["İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
                ["Adel", "Güçlü Al", "Al", "Nötr", "Güçlü Al"],
            ),
            (
                "temel.csv",
                ["İsim", "Ortalama Hacim (3Ay)", "Piyasa değeri", "Gelir", "Fiyat / Kazanç Oranı", "Beta"],
                ["Adel", "4,82M", "12,02Mlr", revenue, pe_ratio, "-0,59"],
            ),
        )
        for filename, headers, row in files:
            out_headers, out_row = self._with_optional_symbol(
                filename, headers, row, symbol_header, symbol_value, table_symbols
            )
            self._write_csv(filename, out_headers, out_row)

    def _snapshot_row(self, snapshot_id: int) -> sqlite3.Row:
        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM snapshot_runs WHERE id = ?", (snapshot_id,)).fetchone()
        self.assertIsNotNone(row)
        return row

    def _mapping_failure_names(self, snapshot_id: int) -> list[str]:
        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT company_name
                FROM snapshot_mapping_failures
                WHERE snapshot_id = ?
                ORDER BY failure_order
                """,
                (snapshot_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def test_imports_revenue_and_pe_ratio(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 1)
        self.assertEqual(payload["price_basis"], "previous_close_to_last_from_daily_change_pct")
        self.assertEqual(payload["source_symbol_count"], 0)
        self.assertEqual(payload["ticker_map_fallback_count"], 1)
        self.assertEqual(payload["fallback_count"], 0)
        self.assertEqual(payload["source_map_disagreement_count"], 0)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].ticker, "ADEL")
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

    def test_daily_import_persists_provenance_metrics(self) -> None:
        self._write_minimal_csv_set("2,10B", "12,77")
        self._write_csv_rows(
            "fiyat.csv",
            ["İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
            [
                ["Adel", "46,10", "47,78", "44,60", "2,60", "5,98%", "11,48M", "18:09:44"],
                ["Unknown Co", "10,00", "11,00", "9,00", "1,00", "1,00%", "1,00M", "18:09:44"],
            ],
        )
        for name, extra in (
            (
                "performans.csv",
                ["Unknown Co", "1,00", "1,00", "1,00", "1,00", "1,00", "1,00"],
            ),
            (
                "teknik.csv",
                ["Unknown Co", "Al", "Al", "Al", "Al"],
            ),
            (
                "temel.csv",
                ["Unknown Co", "1,00M", "1,00Mlr", "1,00B", "10,00", "1,00"],
            ),
        ):
            path = self.settings.data_dir / name
            with path.open("a", encoding="utf-8-sig", newline="") as handle:
                csv.writer(handle).writerow(extra)

        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        row = self._snapshot_row(payload["snapshot_id"])

        self.assertEqual(row["provenance_captured"], 1)
        self.assertEqual(row["skipped_unmapped_count"], payload["skipped_unmapped_count"])
        self.assertEqual(row["rows_read"], payload["rows_read"])
        self.assertEqual(row["mapped_count"], payload["mapped_count"])
        self.assertEqual(row["distinct_tickers"], payload["distinct_generated_tickers"])
        self.assertAlmostEqual(row["ticker_coverage"], payload["ticker_coverage"])
        self.assertEqual(self._mapping_failure_names(payload["snapshot_id"]), ["Unknown Co"])

    def test_legacy_snapshot_rows_are_not_captured(self) -> None:
        snapshot_id = create_snapshot_run(self.settings, date(2026, 4, 21), "test", "data")
        row = self._snapshot_row(snapshot_id)
        self.assertEqual(row["provenance_captured"], 0)
        self.assertIsNone(row["ticker_coverage"])

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
        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            run_count = conn.execute("SELECT COUNT(*) FROM snapshot_runs").fetchone()[0]
            failure_count = conn.execute("SELECT COUNT(*) FROM snapshot_mapping_failures").fetchone()[0]
        self.assertEqual(run_count, 1)
        self.assertEqual(failure_count, 0)

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

    def test_localized_source_symbol_headers_round_trip_without_ticker_map(self) -> None:
        for header in ("Kod", "Sembol", "Symbol"):
            with self.subTest(header=header):
                self._write_minimal_csv_set(
                    "2,10B",
                    "12,77",
                    write_ticker_map=False,
                    symbol_header=header,
                    symbol_value="adel.is",
                )
                payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
                snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

                self.assertEqual(payload["rows_read"], 1)
                self.assertEqual(payload["source_symbol_count"], 1)
                self.assertEqual(payload["ticker_map_fallback_count"], 0)
                self.assertEqual(payload["fallback_count"], 0)
                self.assertEqual(payload["source_map_disagreement_count"], 0)
                self.assertEqual(payload["skipped_unmapped_count"], 0)
                self.assertEqual(len(snapshots), 1)
                self.assertEqual(snapshots[0].ticker, "ADEL")
                self.assertEqual(snapshots[0].company_name, "Adel")

    def test_missing_or_invalid_source_symbol_falls_back_to_ticker_map(self) -> None:
        cases = {
            "missing": {"symbol_header": "Kod", "symbol_value": ""},
            "invalid": {"symbol_header": "Kod", "symbol_value": "12"},
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                self._write_minimal_csv_set("2,10B", "12,77", **kwargs)
                payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
                snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

                self.assertEqual(payload["rows_read"], 1)
                self.assertEqual(payload["source_symbol_count"], 0)
                self.assertEqual(payload["ticker_map_fallback_count"], 1)
                self.assertEqual(payload["fallback_count"], 0)
                self.assertEqual(snapshots[0].ticker, "ADEL")
                if label == "invalid":
                    self.assertEqual(payload["invalid_symbol_count"], 1)
                else:
                    self.assertEqual(payload["invalid_symbol_count"], 0)

    def test_invalid_source_symbol_without_map_is_unmapped_not_prefix_ticker(self) -> None:
        self._write_minimal_csv_set(
            "2,10B",
            "12,77",
            write_ticker_map=False,
            symbol_header="Kod",
            symbol_value="99",
        )
        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 0)
        self.assertEqual(payload["source_symbol_count"], 0)
        self.assertEqual(payload["ticker_map_fallback_count"], 0)
        self.assertEqual(payload["fallback_count"], 1)
        self.assertEqual(payload["skipped_unmapped_count"], 1)
        self.assertEqual(payload["invalid_symbol_count"], 1)
        self.assertEqual(snapshots, [])
        self.assertEqual(self._mapping_failure_names(payload["snapshot_id"]), ["Adel"])

    def test_cross_table_source_symbol_conflict_is_skipped_and_counted(self) -> None:
        self._write_minimal_csv_set(
            "2,10B",
            "12,77",
            write_ticker_map=False,
            symbol_header="Kod",
            table_symbols={
                "fiyat.csv": "ADEL",
                "performans.csv": "THYAO",
                "teknik.csv": "ADEL",
                "temel.csv": "ADEL",
            },
        )
        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 0)
        self.assertEqual(payload["skipped_symbol_conflict_count"], 1)
        self.assertEqual(payload["source_symbol_count"], 0)
        self.assertEqual(payload["skipped_unmapped_count"], 1)
        self.assertEqual(snapshots, [])
        self.assertEqual(self._mapping_failure_names(payload["snapshot_id"]), ["Adel"])

    def test_duplicate_resolved_ticker_collision_is_skipped_and_counted(self) -> None:
        self._write_csv_rows(
            "fiyat.csv",
            ["Kod", "İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
            [
                ["ADEL", "Adel", "46,10", "47,78", "44,60", "2,60", "5,98%", "11,48M", "18:09:44"],
                ["ADEL", "Other Co", "10,00", "11,00", "9,00", "1,00", "1,00%", "1,00M", "18:09:44"],
            ],
        )
        self._write_csv_rows(
            "performans.csv",
            ["Kod", "İsim", "Günlük", "Haftalık", " 1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
            [
                ["ADEL", "Adel", "5,98", "7,21", "36,39", "39,70", "20,37", "347,60"],
                ["ADEL", "Other Co", "1,00", "1,00", "1,00", "1,00", "1,00", "1,00"],
            ],
        )
        self._write_csv_rows(
            "teknik.csv",
            ["Kod", "İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
            [
                ["ADEL", "Adel", "Güçlü Al", "Al", "Nötr", "Güçlü Al"],
                ["ADEL", "Other Co", "Al", "Al", "Al", "Al"],
            ],
        )
        self._write_csv_rows(
            "temel.csv",
            ["Kod", "İsim", "Ortalama Hacim (3Ay)", "Piyasa değeri", "Gelir", "Fiyat / Kazanç Oranı", "Beta"],
            [
                ["ADEL", "Adel", "4,82M", "12,02Mlr", "2,10B", "12,77", "-0,59"],
                ["ADEL", "Other Co", "1,00M", "1,00Mlr", "1,00B", "10,00", "1,00"],
            ],
        )

        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 1)
        self.assertEqual(payload["source_symbol_count"], 1)
        self.assertEqual(payload["skipped_symbol_conflict_count"], 1)
        self.assertEqual(payload["skipped_unmapped_count"], 1)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].ticker, "ADEL")
        self.assertEqual(snapshots[0].company_name, "Adel")
        self.assertEqual(self._mapping_failure_names(payload["snapshot_id"]), ["Other Co"])

    def test_malformed_first_row_does_not_reserve_ticker_for_later_valid_row(self) -> None:
        self._write_csv_rows(
            "fiyat.csv",
            ["Kod", "İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
            [
                ["ADEL", "Adel", "bad-price", "47,78", "44,60", "2,60", "5,98%", "11,48M", "18:09:44"],
                ["ADEL", "Other Co", "10,00", "11,00", "9,00", "1,00", "1,00%", "1,00M", "18:09:44"],
            ],
        )
        self._write_csv_rows(
            "performans.csv",
            ["Kod", "İsim", "Günlük", "Haftalık", " 1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
            [
                ["ADEL", "Adel", "5,98", "7,21", "36,39", "39,70", "20,37", "347,60"],
                ["ADEL", "Other Co", "1,00", "1,00", "1,00", "1,00", "1,00", "1,00"],
            ],
        )
        self._write_csv_rows(
            "teknik.csv",
            ["Kod", "İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
            [
                ["ADEL", "Adel", "Güçlü Al", "Al", "Nötr", "Güçlü Al"],
                ["ADEL", "Other Co", "Al", "Al", "Al", "Al"],
            ],
        )
        self._write_csv_rows(
            "temel.csv",
            ["Kod", "İsim", "Ortalama Hacim (3Ay)", "Piyasa değeri", "Gelir", "Fiyat / Kazanç Oranı", "Beta"],
            [
                ["ADEL", "Adel", "4,82M", "12,02Mlr", "2,10B", "12,77", "-0,59"],
                ["ADEL", "Other Co", "1,00M", "1,00Mlr", "1,00B", "10,00", "1,00"],
            ],
        )

        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["rows_read"], 1)
        self.assertEqual(payload["skipped_malformed_count"], 1)
        self.assertEqual(payload["skipped_symbol_conflict_count"], 0)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].ticker, "ADEL")
        self.assertEqual(snapshots[0].company_name, "Other Co")

    def test_source_symbol_is_preferred_over_ticker_map(self) -> None:
        self._write_minimal_csv_set(
            "2,10B",
            "12,77",
            symbol_header="Kod",
            symbol_value="THYAO",
        )
        payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
        snapshots = get_market_snapshots_for_date(self.settings, date(2026, 4, 21))

        self.assertEqual(payload["source_symbol_count"], 1)
        self.assertEqual(payload["ticker_map_fallback_count"], 0)
        self.assertEqual(payload["source_map_disagreement_count"], 1)
        self.assertEqual(snapshots[0].ticker, "THYAO")

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
