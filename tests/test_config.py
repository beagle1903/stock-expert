from __future__ import annotations

import subprocess
import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from stock_expert.config import _default_db_path, _load_dotenv, get_settings


class DefaultDatabasePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_dir = Path("C:/repo")
        self.data_dir = self.base_dir / "data"

    @patch.dict("os.environ", {}, clear=True)
    def test_main_uses_primary_database(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout="main\n", stderr="")
        with patch("stock_expert.config.subprocess.run", return_value=completed):
            path = _default_db_path(self.base_dir, self.data_dir)

        self.assertEqual(path, self.data_dir / "stock_expert.db")

    @patch.dict("os.environ", {}, clear=True)
    def test_detached_head_uses_isolated_database(self) -> None:
        branch = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        sha = subprocess.CompletedProcess([], 0, stdout="abc1234\n", stderr="")
        with patch("stock_expert.config.subprocess.run", side_effect=[branch, sha]):
            path = _default_db_path(self.base_dir, self.data_dir)

        self.assertEqual(path, self.data_dir / "stock_expert_detached_abc1234.db")

    @patch.dict("os.environ", {}, clear=True)
    def test_git_failure_uses_isolated_unknown_database(self) -> None:
        with patch("stock_expert.config.subprocess.run", side_effect=OSError("git missing")):
            path = _default_db_path(self.base_dir, self.data_dir)

        self.assertEqual(path, self.data_dir / "stock_expert_detached_unknown.db")

    @patch.dict("os.environ", {}, clear=True)
    def test_feature_branch_and_database_override_paths(self) -> None:
        feature = subprocess.CompletedProcess([], 0, stdout="codex/Add Indicators\n", stderr="")
        with patch("stock_expert.config.subprocess.run", return_value=feature):
            path = _default_db_path(self.base_dir, self.data_dir)
        self.assertEqual(path, self.data_dir / "stock_expert_codex_add_indicators.db")

        os.environ["STOCK_EXPERT_DB_PATH"] = "data/custom.db"
        self.assertEqual(
            _default_db_path(self.base_dir, self.data_dir),
            self.base_dir / "data/custom.db",
        )

    @patch.dict("os.environ", {"EXISTING": "keep"}, clear=True)
    def test_dotenv_loads_valid_missing_values_without_overwriting(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"config_{uuid.uuid4().hex}"
        base_dir.mkdir(parents=True)
        try:
            (base_dir / ".env").write_text(
                "\n# comment\nINVALID\nNEW_VALUE='loaded'\nEXISTING=replaced\n",
                encoding="utf-8",
            )

            _load_dotenv(base_dir)

            self.assertEqual(os.environ["NEW_VALUE"], "loaded")
            self.assertEqual(os.environ["EXISTING"], "keep")
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

    def test_get_settings_builds_paths_from_module_location(self) -> None:
        project = Path(__file__).resolve().parent.parent / ".test_tmp" / f"settings_{uuid.uuid4().hex}"
        fake_module = project / "stock_expert" / "config.py"
        fake_module.parent.mkdir(parents=True)
        try:
            with (
                patch("stock_expert.config.__file__", str(fake_module)),
                patch("stock_expert.config._load_dotenv") as load_dotenv,
                patch(
                    "stock_expert.config._default_db_path",
                    return_value=project / "data/test.db",
                ),
            ):
                settings = get_settings()

            self.assertEqual(settings.base_dir, project)
            self.assertTrue(settings.data_dir.exists())
            load_dotenv.assert_called_once_with(project)
        finally:
            shutil.rmtree(project, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
