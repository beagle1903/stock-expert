from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import ANY, patch

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

    def test_direct_daily_picks_and_review_commands_route_arguments(self) -> None:
        cases = [
            (
                ["stocks", "daily", "--date", "2026-04-21"],
                "daily_summary",
                {"args": (self.settings, cli.date(2026, 4, 21)), "kwargs": {}},
            ),
            (
                ["stocks", "picks", "--date", "2026-04-21", "--dry-run"],
                "picks_output",
                {"args": (self.settings, cli.date(2026, 4, 21)), "kwargs": {"dry_run": True}},
            ),
            (
                ["stocks", "review", "--date", "2026-04-21", "--dry-run"],
                "review_output",
                {"args": (self.settings, cli.date(2026, 4, 21)), "kwargs": {"dry_run": True}},
            ),
        ]
        for argv, target, expected in cases:
            with self.subTest(command=argv[1]):
                with (
                    patch("stock_expert.cli.get_settings", return_value=self.settings),
                    patch(f"stock_expert.cli.{target}", return_value="output") as command,
                    patch("sys.argv", argv),
                    redirect_stdout(io.StringIO()) as stdout,
                ):
                    self.assertEqual(cli.main(), 0)

                command.assert_called_once_with(*expected["args"], **expected["kwargs"])
                self.assertIn("output", stdout.getvalue())

    def test_download_and_excel_import_commands_route_all_options(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.download_ohlcv_command", return_value="downloaded") as download,
            patch(
                "sys.argv",
                [
                    "stocks",
                    "download-ohlcv",
                    "--tickers",
                    "ADEL",
                    "THYAO.IS",
                    "--days",
                    "10",
                    "--output",
                    "data/out.csv",
                    "--import-db",
                    "--pause-seconds",
                    "0.2",
                    "--max-retries",
                    "2",
                ],
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        download.assert_called_once_with(
            settings=self.settings,
            tickers=["ADEL", "THYAO.IS"],
            days=10,
            output_path="data/out.csv",
            import_db=True,
            pause_seconds=0.2,
            max_retries=2,
        )

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_ohlcv_excel_command", return_value="imported") as bulk_import,
            patch(
                "sys.argv",
                [
                    "stocks",
                    "import-ohlcv-excel",
                    "--input",
                    "data/tickers.xlsx",
                    "--start-date",
                    "2026-04-01",
                    "--end-date",
                    "2026-04-21",
                    "--pause-seconds",
                    "0.3",
                    "--max-retries",
                    "3",
                    "--batch-size",
                    "10",
                    "--batch-pause-seconds",
                    "4",
                ],
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        bulk_import.assert_called_once_with(
            settings=self.settings,
            input_path="data/tickers.xlsx",
            start_date="2026-04-01",
            end_date="2026-04-21",
            pause_seconds=0.3,
            max_retries=3,
            batch_size=10,
            batch_pause_seconds=4.0,
        )

    def test_daily_csv_and_folder_import_commands_route_arguments(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_command", return_value="csv") as csv_import,
            patch(
                "sys.argv",
                ["stocks", "import-daily-csv", "--date", "2026-04-21", "--data-dir", "data/live"],
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        csv_import.assert_called_once_with(
            settings=self.settings,
            snapshot_date="2026-04-21",
            data_dir="data/live",
        )

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_folder_command", return_value="folder") as folder_import,
            patch("sys.argv", ["stocks", "import-daily-folder", "--folder", "data/20260421"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        folder_import.assert_called_once_with(settings=self.settings, folder="data/20260421")

    def test_midday_routine_uses_dry_run_review(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_command", return_value=json.dumps({"ok": True})),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.review_output", return_value="review") as review_output,
            patch("sys.argv", ["stocks", "midday-routine", "--date", "2026-04-21"]),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        review_output.assert_called_once_with(
            self.settings,
            cli.date(2026, 4, 21),
            dry_run=True,
            ranking_context=ANY,
        )
        output = stdout.getvalue()
        self.assertIn('"routine": "midday-routine"', output)
        self.assertIn("Market Context:", output)
        self.assertIn("Pick List:", output)
        self.assertIn("Dry-Run Review:", output)

    def test_routine_uses_persisted_review(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_command", return_value=json.dumps({"ok": True})),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market") as market_context_output,
            patch("stock_expert.cli.picks_output", return_value="picks") as picks_output,
            patch("stock_expert.cli.bucketed_strategy_comparison_output", return_value="bucketed") as bucketed_strategy_comparison_output,
            patch("stock_expert.cli.downside_risk_output", return_value="downside") as downside_risk_output,
            patch("stock_expert.cli.review_output", return_value="review") as review_output,
            patch("sys.argv", ["stocks", "routine", "--date", "2026-04-21"]),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        market_context_output.assert_called_once_with(cli.date(2026, 4, 21))
        bucketed_strategy_comparison_output.assert_called_once_with(
            self.settings,
            cli.date(2026, 4, 21),
            ranking_context=ANY,
        )
        downside_risk_output.assert_called_once_with(
            self.settings,
            cli.date(2026, 4, 21),
            ranking_context=ANY,
        )
        self.assertEqual(
            picks_output.call_args_list,
            [
                unittest.mock.call(
                    self.settings,
                    cli.date(2026, 4, 21),
                    ranking_context=ANY,
                ),
            ],
        )
        review_output.assert_called_once_with(
            self.settings,
            cli.date(2026, 4, 21),
            ranking_context=ANY,
        )
        output = stdout.getvalue()
        self.assertIn('"routine": "routine"', output)
        self.assertIn("Pick List:", output)
        self.assertIn("Review:", output)
        self.assertIn("Score-Ranked vs Bucketed Review Comparison:", output)
        self.assertIn("Downside Risk Diagnostic:", output)
        self.assertNotIn("No-Chase", output)


if __name__ == "__main__":
    unittest.main()
