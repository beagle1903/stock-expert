from __future__ import annotations

import csv
import json
import os
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
    load_csv_bundle,
    publish_csv_bundle,
    publish_extracted_tables,
    publish_uploaded_csvs_command,
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

    def test_rejects_invalid_payload_shapes(self) -> None:
        with self.assertRaisesRegex(InvestingCsvError, "tables object"):
            validate_extracted_tables({}, min_rows=2)

        payload = self._payload()
        payload["tables"]["fiyat.csv"]["rows"][0] = ["Adel"]
        with self.assertRaisesRegex(InvestingCsvError, "expected 8"):
            validate_extracted_tables(payload, min_rows=2)

        payload = self._payload()
        payload["tables"]["fiyat.csv"]["rows"][0][1] = 30.8
        with self.assertRaisesRegex(InvestingCsvError, "non-text"):
            validate_extracted_tables(payload, min_rows=2)

        payload = self._payload()
        payload["tables"]["fiyat.csv"]["rows"][0][0] = "  "
        with self.assertRaisesRegex(InvestingCsvError, "empty company"):
            validate_extracted_tables(payload, min_rows=2)

    def test_rejects_company_coverage_drift(self) -> None:
        payload = self._payload()
        payload["tables"]["temel.csv"]["rows"][1][0] = "Different Company"

        with self.assertRaisesRegex(InvestingCsvError, "company coverage differs"):
            validate_extracted_tables(payload, min_rows=2)

    def test_rejects_invalid_minimum_row_setting(self) -> None:
        with self.assertRaisesRegex(ValueError, "min_rows"):
            validate_extracted_tables(self._payload(), min_rows=0)

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

    def test_publishes_uploaded_csv_bundle_atomically(self) -> None:
        source = self.base_dir / "uploaded"
        destination = self.base_dir / "published"
        publish_extracted_tables(self._payload(), destination=source, min_rows=2)

        counts = publish_csv_bundle(source, destination=destination, min_rows=2)

        self.assertEqual(counts, {filename: 2 for filename in CSV_HEADERS})
        self.assertTrue((destination / "fiyat.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(
            (destination / "temel.csv").read_text(encoding="utf-8-sig").splitlines()[1].split(",")[0].strip('"'),
            "Adel",
        )

    def test_invalid_uploaded_csv_bundle_does_not_replace_existing_files(self) -> None:
        source = self.base_dir / "uploaded"
        destination = self.base_dir / "published"
        publish_extracted_tables(self._payload(), destination=source, min_rows=2)
        publish_extracted_tables(self._payload(), destination=destination, min_rows=2)
        (source / "teknik.csv").write_text("bad\n", encoding="utf-8")

        with self.assertRaisesRegex(InvestingCsvError, "header mismatch"):
            publish_csv_bundle(source, destination=destination, min_rows=2)

        self.assertIn("Adel", (destination / "teknik.csv").read_text(encoding="utf-8-sig"))

    def test_uploaded_bundle_loader_reports_missing_empty_and_invalid_utf8(self) -> None:
        missing = self.base_dir / "missing"
        missing.mkdir()
        with self.assertRaisesRegex(InvestingCsvError, "missing fiyat.csv"):
            load_csv_bundle(missing)

        empty = self.base_dir / "empty"
        empty.mkdir()
        (empty / "fiyat.csv").write_bytes(b"")
        with self.assertRaisesRegex(InvestingCsvError, "empty"):
            load_csv_bundle(empty)

        invalid = self.base_dir / "invalid"
        invalid.mkdir()
        (invalid / "fiyat.csv").write_bytes(b"\xff")
        with self.assertRaisesRegex(InvestingCsvError, "valid UTF-8"):
            load_csv_bundle(invalid)

    def test_uploaded_command_publishes_and_reports_paths(self) -> None:
        source = self.base_dir / "uploaded"
        destination = self.base_dir / "published"
        publish_extracted_tables(self._payload(), destination=source, min_rows=2)
        settings = Settings(
            base_dir=self.base_dir,
            data_dir=self.base_dir / "data",
            db_path=self.base_dir / "data" / "test.db",
        )

        result = json.loads(
            publish_uploaded_csvs_command(
                settings,
                source_dir="uploaded",
                data_dir="published",
                min_rows=2,
            )
        )

        self.assertEqual(result["rows"], {filename: 2 for filename in CSV_HEADERS})
        self.assertEqual(result["publication"], "atomic")
        self.assertEqual(result["destination_dir"], str(destination))

    def test_publish_rollback_restores_existing_files(self) -> None:
        source = self.base_dir / "uploaded"
        destination = self.base_dir / "published"
        publish_extracted_tables(self._payload(), destination=source, min_rows=2)
        publish_extracted_tables(self._payload(), destination=destination, min_rows=2)

        real_replace = os.replace

        def fail_on_second_file(source_path: Path, target_path: Path) -> None:
            if source_path.name == "performans.csv" and target_path == destination / "performans.csv":
                raise OSError("simulated replace failure")
            real_replace(source_path, target_path)

        with patch(
            "stock_expert.investing_csv.os.replace",
            side_effect=fail_on_second_file,
        ):
            with self.assertRaisesRegex(OSError, "simulated replace failure"):
                publish_csv_bundle(source, destination=destination, min_rows=2)

        for filename in CSV_HEADERS:
            self.assertIn("Adel", (destination / filename).read_text(encoding="utf-8-sig"))

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
