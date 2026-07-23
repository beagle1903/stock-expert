from __future__ import annotations

import csv
import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from stock_expert.config import Settings
from stock_expert.investing_csv import (
    CSV_HEADERS,
    InvestingCsvError,
    publish_extracted_tables,
    refresh_investing_csvs_command,
    validate_extracted_tables,
)


class InvestingCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"investing_csv_{uuid.uuid4().hex}"
        self.base_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def _payload(self) -> dict[str, object]:
        companies = ["Adel", "Adese Gayrimenkul"]
        values = {
            "fiyat.csv": [
                ["30,80", "31,28", "30,60", "-0,04", "-0,13%", "1,17M", "18:09:59"],
                ["0,930", "0,950", "0,910", "0,010", "1,09%", "171,89M", "18:09:59"],
            ],
            "performans.csv": [
                ["-0,13", "0,98", "-3,57", "-6,67", "0,26", "26,90"],
                ["1,09", "0,00", "-7,00", "-38,82", "-67,55", "175,15"],
            ],
            "teknik.csv": [
                ["Güçlü Sat", "Sat", "Güçlü Sat", "Sat"],
                ["Güçlü Al", "Sat", "Güçlü Sat", "Sat"],
            ],
            "temel.csv": [
                ["5,79M", "8,01Mlr", "2,56B", "-29,06", "-0,54"],
                ["231,37M", "4,64Mlr", "1,34B", "17,06", "1,00"],
            ],
        }
        tables: dict[str, object] = {}
        for filename, headers in CSV_HEADERS.items():
            tables[filename] = {
                "headers": [header.strip() for header in headers],
                "rows": [[company, *row] for company, row in zip(companies, values[filename], strict=True)],
            }
        return {"tables": tables}

    def test_validates_matching_four_table_bundle(self) -> None:
        counts = validate_extracted_tables(self._payload(), min_rows=2)

        self.assertEqual(counts, {filename: 2 for filename in CSV_HEADERS})

    def test_rejects_incomplete_company_coverage(self) -> None:
        payload = self._payload()
        payload["tables"]["temel.csv"]["rows"].pop()

        with self.assertRaisesRegex(InvestingCsvError, "at least 2"):
            validate_extracted_tables(payload, min_rows=2)

    def test_rejects_header_drift(self) -> None:
        payload = self._payload()
        payload["tables"]["teknik.csv"]["headers"][1] = "Saat"

        with self.assertRaisesRegex(InvestingCsvError, "header mismatch"):
            validate_extracted_tables(payload, min_rows=2)

    def test_publishes_quoted_utf8_csv_bundle(self) -> None:
        counts = publish_extracted_tables(self._payload(), destination=self.base_dir, min_rows=2)

        self.assertEqual(counts["fiyat.csv"], 2)
        for filename, expected_headers in CSV_HEADERS.items():
            with (self.base_dir / filename).open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], expected_headers)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[1][0], "Adel")
        self.assertTrue((self.base_dir / "fiyat.csv").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_invalid_bundle_does_not_replace_existing_files(self) -> None:
        for filename in CSV_HEADERS:
            (self.base_dir / filename).write_text("existing", encoding="utf-8")
        payload = self._payload()
        payload["tables"]["fiyat.csv"]["rows"] = []

        with self.assertRaises(InvestingCsvError):
            publish_extracted_tables(payload, destination=self.base_dir, min_rows=2)

        for filename in CSV_HEADERS:
            self.assertEqual((self.base_dir / filename).read_text(encoding="utf-8"), "existing")

    def test_refresh_command_runs_extractor_and_publishes_bundle(self) -> None:
        script = self.base_dir / "scripts" / "investing_csv_extract.mjs"
        script.parent.mkdir()
        script.write_text("// test", encoding="utf-8")
        settings = Settings(
            base_dir=self.base_dir,
            data_dir=self.base_dir / "data",
            db_path=self.base_dir / "data" / "test.db",
        )

        def complete_extraction(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_text(json.dumps(self._payload()), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with (
            patch("stock_expert.investing_csv.shutil.which", return_value="node"),
            patch("stock_expert.investing_csv.subprocess.run", side_effect=complete_extraction) as run,
        ):
            result = json.loads(
                refresh_investing_csvs_command(
                    settings,
                    data_dir="data/live",
                    min_rows=2,
                    max_more_clicks=4,
                    timeout_seconds=30,
                )
            )

        self.assertEqual(result["rows"], {filename: 2 for filename in CSV_HEADERS})
        self.assertEqual(run.call_count, 1)
        command = run.call_args.args[0]
        self.assertIn("--max-more-clicks", command)
        self.assertTrue((self.base_dir / "data" / "live" / "fiyat.csv").exists())
        self.assertFalse(any((self.base_dir / ".test_tmp").glob("investing-csv-*")))

    def test_refresh_command_reports_browser_failure_without_publication(self) -> None:
        script = self.base_dir / "scripts" / "investing_csv_extract.mjs"
        script.parent.mkdir()
        script.write_text("// test", encoding="utf-8")
        settings = Settings(
            base_dir=self.base_dir,
            data_dir=self.base_dir / "data",
            db_path=self.base_dir / "data" / "test.db",
        )

        with (
            patch("stock_expert.investing_csv.shutil.which", return_value="node"),
            patch(
                "stock_expert.investing_csv.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="access challenge"),
            ),
        ):
            with self.assertRaisesRegex(InvestingCsvError, "access challenge"):
                refresh_investing_csvs_command(settings, min_rows=2, timeout_seconds=30)

        self.assertFalse((self.base_dir / "data" / "fiyat.csv").exists())
