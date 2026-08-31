from __future__ import annotations

import csv
import hashlib
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path

from stock_expert.config import Settings
from stock_expert.database import connect, init_db
from stock_expert.investing_csv import CSV_HEADERS
from stock_expert.workspace_bundle import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    DATABASE_MEMBER,
    WorkspaceBundleError,
    export_workspace_bundle,
    import_workspace_bundle,
)


class WorkspaceBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parent.parent / ".test_tmp" / f"workspace_bundle_{uuid.uuid4().hex}"
        self.source_base = self.root / "source"
        self.target_base = self.root / "target"
        self.source_data = self.source_base / "data"
        self.target_data = self.target_base / "data"
        self.source_data.mkdir(parents=True)
        self.target_data.mkdir(parents=True)
        self.source_settings = Settings(
            base_dir=self.source_base,
            data_dir=self.source_data,
            db_path=self.source_data / "stock_expert.db",
        )
        self.target_settings = Settings(
            base_dir=self.target_base,
            data_dir=self.target_data,
            db_path=self.target_data / "stock_expert.db",
        )
        init_db(self.source_settings)
        self._write_inputs(self.source_data)
        with connect(self.source_settings) as connection:
            connection.execute(
                "INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir) VALUES (?, ?, ?)",
                ("2026-08-28", "daily_csv", "data"),
            )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_inputs(self, directory: Path) -> None:
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
        companies = ["Adel", "Adese Gayrimenkul"]
        for filename, headers in CSV_HEADERS.items():
            with (directory / filename).open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
                writer.writerow(headers)
                writer.writerows([[company, *row] for company, row in zip(companies, values[filename], strict=True)])

    def test_round_trip_restores_database_and_inputs(self) -> None:
        bundle = self.source_base / "workspace.zip"
        exported = export_workspace_bundle(self.source_settings, bundle, min_rows=2)

        imported = import_workspace_bundle(self.target_settings, bundle, min_rows=2)

        self.assertEqual(exported["rows"], {filename: 2 for filename in CSV_HEADERS})
        self.assertEqual(imported["rows"], {filename: 2 for filename in CSV_HEADERS})
        self.assertTrue(imported["inputs_published"])
        self.assertTrue((self.target_data / "fiyat.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        with connect(self.target_settings) as connection:
            row = connection.execute("SELECT snapshot_date FROM snapshot_runs").fetchone()
        self.assertEqual(row["snapshot_date"], "2026-08-28")

    def test_existing_database_requires_explicit_replace(self) -> None:
        bundle = self.source_base / "workspace.zip"
        export_workspace_bundle(self.source_settings, bundle, min_rows=2)
        init_db(self.target_settings)
        with connect(self.target_settings) as connection:
            connection.execute(
                "INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir) VALUES (?, ?, ?)",
                ("2026-01-01", "old", "old"),
            )

        with self.assertRaisesRegex(WorkspaceBundleError, "replace-database"):
            import_workspace_bundle(self.target_settings, bundle, min_rows=2)

        with connect(self.target_settings) as connection:
            row = connection.execute("SELECT snapshot_date FROM snapshot_runs").fetchone()
        self.assertEqual(row["snapshot_date"], "2026-01-01")

    def test_replace_database_creates_recoverable_backup(self) -> None:
        bundle = self.source_base / "workspace.zip"
        export_workspace_bundle(self.source_settings, bundle, min_rows=2)
        init_db(self.target_settings)

        imported = import_workspace_bundle(
            self.target_settings,
            bundle,
            replace_database=True,
            min_rows=2,
        )

        self.assertTrue(imported["database_replaced"])
        self.assertIsNotNone(imported["database_backup"])
        self.assertTrue(Path(imported["database_backup"]).is_file())

    def test_database_only_bundle_does_not_publish_inputs(self) -> None:
        bundle = self.source_base / "database-only.zip"
        export_workspace_bundle(self.source_settings, bundle, include_inputs=False)

        imported = import_workspace_bundle(self.target_settings, bundle)

        self.assertFalse(imported["inputs_published"])
        self.assertFalse(imported["database_replaced"])
        self.assertFalse((self.target_data / "fiyat.csv").exists())
        self.assertTrue(self.target_settings.db_path.is_file())

    def test_invalid_zip_is_rejected(self) -> None:
        broken = self.source_base / "broken.zip"
        broken.write_text("not a zip", encoding="utf-8")

        with self.assertRaisesRegex(WorkspaceBundleError, "valid ZIP"):
            import_workspace_bundle(self.target_settings, broken)

    def test_unsafe_archive_member_is_rejected(self) -> None:
        unsafe = self.source_base / "unsafe.zip"
        with zipfile.ZipFile(unsafe, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("../escape", b"no")

        with self.assertRaisesRegex(WorkspaceBundleError, "unsafe archive member"):
            import_workspace_bundle(self.target_settings, unsafe)

    def test_invalid_database_member_is_rejected(self) -> None:
        invalid = self.source_base / "invalid-database.zip"
        content = b"not sqlite"
        manifest = {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "created_at": "2026-08-30T00:00:00+00:00",
            "includes_inputs": False,
            "input_rows": {},
            "files": {
                DATABASE_MEMBER: {
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            },
        }
        with zipfile.ZipFile(invalid, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr(DATABASE_MEMBER, content)

        with self.assertRaisesRegex(WorkspaceBundleError, "not valid SQLite"):
            import_workspace_bundle(self.target_settings, invalid)

    def test_tampered_member_is_rejected(self) -> None:
        bundle = self.source_base / "workspace.zip"
        export_workspace_bundle(self.source_settings, bundle, min_rows=2)
        tampered = self.source_base / "tampered.zip"
        with zipfile.ZipFile(bundle, "r") as source:
            with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for name in source.namelist():
                    content = source.read(name)
                    if name == "inputs/fiyat.csv":
                        content = content.replace(b"Adel", b"Other")
                    target.writestr(name, content)

        with self.assertRaisesRegex(WorkspaceBundleError, "checksum mismatch"):
            import_workspace_bundle(self.target_settings, tampered, min_rows=2)


if __name__ == "__main__":
    unittest.main()
