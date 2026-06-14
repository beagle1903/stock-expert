from __future__ import annotations

import csv
import io
import json
import shutil
import unittest
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from stock_expert.config import Settings
from stock_expert.yahoo import (
    download_ohlcv_command,
    fetch_yahoo_ohlcv,
    fetch_yahoo_ohlcv_with_retry,
    import_ohlcv_excel_command,
    load_tickers_from_excel,
    normalize_yahoo_symbol,
    write_ohlcv_csv,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class YahooTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"yahoo_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.settings.base_dir, ignore_errors=True)

    def _history(self) -> list[dict[str, object]]:
        return [
            {
                "date": "2026-04-20",
                "open": 10.0,
                "high": 12.0,
                "low": 9.0,
                "close": 11.0,
                "volume": 1000,
            },
            {
                "date": "2026-04-21",
                "open": 11.0,
                "high": 13.0,
                "low": 10.0,
                "close": 12.0,
                "volume": 2000,
            },
        ]

    def test_normalize_yahoo_symbol_handles_local_and_qualified_codes(self) -> None:
        self.assertEqual(normalize_yahoo_symbol(" adel "), ("ADEL.IS", "ADEL"))
        self.assertEqual(normalize_yahoo_symbol("adel.is"), ("ADEL.IS", "ADEL"))

    def test_fetch_yahoo_ohlcv_parses_rows_and_skips_null_quotes(self) -> None:
        timestamps = [
            int(datetime(2026, 4, 20, tzinfo=UTC).timestamp()),
            int(datetime(2026, 4, 21, tzinfo=UTC).timestamp()),
        ]
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10.12345, None],
                                    "high": [12.0, 13.0],
                                    "low": [9.0, 10.0],
                                    "close": [11.98765, 12.0],
                                    "volume": [1000, 2000],
                                }
                            ]
                        },
                    }
                ]
            }
        }

        with patch("stock_expert.yahoo.urlopen", return_value=_FakeResponse(payload)) as urlopen:
            rows = fetch_yahoo_ohlcv("ADEL.IS", 5)

        self.assertEqual(
            rows,
            [
                {
                    "date": "2026-04-20",
                    "open": 10.1235,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.9877,
                    "volume": 1000,
                }
            ],
        )
        self.assertIn("ADEL.IS", urlopen.call_args.args[0])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 20)

    def test_retry_uses_retry_after_for_http_429(self) -> None:
        error = HTTPError("https://example.test", 429, "rate limited", {"Retry-After": "2"}, io.BytesIO())
        with (
            patch("stock_expert.yahoo.fetch_yahoo_ohlcv", side_effect=[error, self._history()]),
            patch("stock_expert.yahoo.random.uniform", return_value=0.0),
            patch("stock_expert.yahoo.time.sleep") as sleep,
        ):
            rows = fetch_yahoo_ohlcv_with_retry("ADEL.IS", 5, max_retries=1, pause_seconds=0.5)

        self.assertEqual(rows, self._history())
        sleep.assert_called_once_with(2.0)

    def test_retry_handles_transient_url_error_and_then_raises_when_exhausted(self) -> None:
        error = URLError("offline")
        with (
            patch("stock_expert.yahoo.fetch_yahoo_ohlcv", side_effect=[error, self._history()]),
            patch("stock_expert.yahoo.random.uniform", return_value=0.0),
            patch("stock_expert.yahoo.time.sleep") as sleep,
        ):
            rows = fetch_yahoo_ohlcv_with_retry("ADEL.IS", 5, max_retries=1, pause_seconds=0.25)

        self.assertEqual(rows, self._history())
        sleep.assert_called_once_with(0.25)

        with patch("stock_expert.yahoo.fetch_yahoo_ohlcv", side_effect=error):
            with self.assertRaises(URLError):
                fetch_yahoo_ohlcv_with_retry("ADEL.IS", 5, max_retries=0, pause_seconds=0.25)

    def test_load_tickers_from_minimal_excel_deduplicates_and_filters(self) -> None:
        workbook = self.settings.base_dir / "tickers.xlsx"
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData>
            <row><c t="inlineStr"><is><t>KOD</t></is></c></row>
            <row><c t="inlineStr"><is><t>adel</t></is></c></row>
            <row><c t="inlineStr"><is><t>ADEL</t></is></c></row>
            <row><c t="inlineStr"><is><t>THY-AO</t></is></c></row>
            <row><c t="inlineStr"><is><t>TOO-LONG-CODE</t></is></c></row>
            <row></row>
          </sheetData>
        </worksheet>"""
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", xml)

        self.assertEqual(load_tickers_from_excel(workbook), ["ADEL", "THYAO"])

    def test_write_ohlcv_csv_writes_header_and_rows(self) -> None:
        output = self.settings.data_dir / "out.csv"
        row = {
            "ticker": "ADEL",
            "yahoo_symbol": "ADEL.IS",
            **self._history()[0],
        }

        write_ohlcv_csv(output, [row])

        with output.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["ticker"], "ADEL")
        self.assertEqual(rows[0]["close"], "11.0")

    def test_download_command_records_success_failure_and_optional_import(self) -> None:
        failure = URLError("offline")
        with (
            patch(
                "stock_expert.yahoo.fetch_yahoo_ohlcv_with_retry",
                side_effect=[self._history(), failure],
            ),
            patch("stock_expert.yahoo.time.sleep") as sleep,
            patch("stock_expert.yahoo.init_db") as init_db,
            patch("stock_expert.yahoo.upsert_prices") as upsert_prices,
        ):
            payload = json.loads(
                download_ohlcv_command(
                    self.settings,
                    tickers=["ADEL", "FAIL"],
                    days=5,
                    output_path="data/download.csv",
                    import_db=True,
                    pause_seconds=0.1,
                    max_retries=2,
                )
            )

        self.assertEqual(payload["downloaded_tickers"], ["ADEL"])
        self.assertEqual(payload["rows_written"], 2)
        self.assertEqual(payload["rows_imported"], 2)
        self.assertEqual(payload["failures"][0]["ticker"], "FAIL")
        self.assertTrue((self.settings.data_dir / "download.csv").exists())
        init_db.assert_called_once_with(self.settings)
        self.assertEqual(len(upsert_prices.call_args.args[1]), 2)
        sleep.assert_called_once_with(0.1)

    def test_download_command_can_export_without_database_import(self) -> None:
        with (
            patch("stock_expert.yahoo.fetch_yahoo_ohlcv_with_retry", return_value=self._history()),
            patch("stock_expert.yahoo.init_db") as init_db,
            patch("stock_expert.yahoo.upsert_prices") as upsert_prices,
        ):
            payload = json.loads(
                download_ohlcv_command(
                    self.settings,
                    tickers=["ADEL"],
                    days=5,
                    output_path="data/download.csv",
                    import_db=False,
                    pause_seconds=0.0,
                    max_retries=0,
                )
            )

        self.assertEqual(payload["rows_imported"], 0)
        init_db.assert_not_called()
        upsert_prices.assert_not_called()

    def test_excel_import_filters_range_batches_and_reports_failures(self) -> None:
        failure = HTTPError("https://example.test", 500, "bad", {}, io.BytesIO())
        histories = [self._history(), self._history(), failure]
        with (
            patch("stock_expert.yahoo.load_tickers_from_excel", return_value=["ADEL", "THYAO", "FAIL"]),
            patch("stock_expert.yahoo.fetch_yahoo_ohlcv_with_retry", side_effect=histories),
            patch("stock_expert.yahoo.time.sleep") as sleep,
            patch("stock_expert.yahoo.init_db") as init_db,
            patch("stock_expert.yahoo.upsert_prices") as upsert_prices,
        ):
            payload = json.loads(
                import_ohlcv_excel_command(
                    self.settings,
                    input_path="tickers.xlsx",
                    start_date="2026-04-21",
                    end_date="2026-04-21",
                    pause_seconds=0.1,
                    max_retries=1,
                    batch_size=2,
                    batch_pause_seconds=0.5,
                )
            )

        self.assertEqual(payload["parsed_tickers"], 3)
        self.assertEqual(payload["rows_written"], 2)
        self.assertEqual(payload["rows_imported"], 2)
        self.assertEqual(payload["failure_count"], 1)
        self.assertEqual(payload["sample_failures"][0]["ticker"], "FAIL")
        init_db.assert_called_once_with(self.settings)
        self.assertEqual(len(upsert_prices.call_args.args[1]), 2)
        self.assertEqual(sleep.call_count, 3)


if __name__ == "__main__":
    unittest.main()
