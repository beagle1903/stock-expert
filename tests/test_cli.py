from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from stock_expert import cli
from stock_expert.config import Settings


class CliRoutineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(base_dir=".", data_dir="data", db_path="data/test.db")

    def test_parser_accepts_midday_routine(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["midday-routine", "--date", "2026-04-21"])
        self.assertEqual(args.command, "midday-routine")
        self.assertEqual(args.as_of, "2026-04-21")

    def test_midday_routine_uses_dry_run_review(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_command", return_value=json.dumps({"ok": True})),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.review_output", return_value="review") as review_output,
            patch("sys.argv", ["stocks", "midday-routine", "--date", "2026-04-21"]),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        review_output.assert_called_once_with(self.settings, cli.date(2026, 4, 21), dry_run=True)
        output = stdout.getvalue()
        self.assertIn('"routine": "midday-routine"', output)
        self.assertIn("Dry-Run Review:", output)

    def test_routine_uses_persisted_review(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_command", return_value=json.dumps({"ok": True})),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.review_output", return_value="review") as review_output,
            patch("sys.argv", ["stocks", "routine", "--date", "2026-04-21"]),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        review_output.assert_called_once_with(self.settings, cli.date(2026, 4, 21))
        output = stdout.getvalue()
        self.assertIn('"routine": "routine"', output)
        self.assertIn("Review:", output)


if __name__ == "__main__":
    unittest.main()
