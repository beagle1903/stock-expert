from __future__ import annotations

import io
import json
import shutil
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import ANY, patch

from stock_expert import cli, services
from stock_expert.config import Settings
from stock_expert.daily_csv import DailyCsvError
from stock_expert.database import (
    connect,
    init_db,
    persist_daily_snapshot,
    persist_review_bundle,
    replace_picks_for_date,
)
from stock_expert.investing_csv import InvestingCsvError
from stock_expert.models import PickRow, Weights
from stock_expert.services import ReviewEvidenceConflict


class CliRoutineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(base_dir=".", data_dir="data", db_path="data/test.db")
        # These routing tests mock every service; keep the evidence guard off
        # the relative test database path. The guard has its own tests below.
        evidence_check = patch("stock_expert.cli.check_review_evidence")
        self.check_review_evidence = evidence_check.start()
        self.addCleanup(evidence_check.stop)

    def test_parser_rejects_midday_routine(self) -> None:
        parser = cli.build_parser()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["midday-routine", "--date", "2026-04-21"])

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
            patch("stock_expert.cli.refresh_investing_csvs_command", return_value="refreshed") as refresh,
            patch(
                "sys.argv",
                [
                    "stocks",
                    "refresh-investing-csvs",
                    "--data-dir",
                    "data/live",
                    "--min-rows",
                    "600",
                    "--max-more-clicks",
                    "9",
                    "--timeout-seconds",
                    "240",
                    "--browser",
                    "C:/browser.exe",
                    "--headless",
                ],
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        refresh.assert_called_once_with(
            settings=self.settings,
            data_dir="data/live",
            min_rows=600,
            max_more_clicks=9,
            timeout_seconds=240,
            browser_path="C:/browser.exe",
            headless=True,
        )

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch(
                "stock_expert.cli.refresh_investing_csvs_command",
                side_effect=InvestingCsvError("access challenge"),
            ),
            patch("sys.argv", ["stocks", "refresh-investing-csvs"]),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(cli.main(), 1)

        self.assertIn("access challenge", stderr.getvalue())

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.import_daily_csv_folder_command", return_value="folder") as folder_import,
            patch("sys.argv", ["stocks", "import-daily-folder", "--folder", "data/20260421"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        folder_import.assert_called_once_with(settings=self.settings, folder="data/20260421")

    def test_routine_reports_unsafe_daily_csv_without_running_strategy(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch(
                "stock_expert.cli.import_daily_csv_command",
                side_effect=DailyCsvError("ticker coverage is too low"),
            ),
            patch("stock_expert.cli.daily_summary") as daily_summary,
            patch("sys.argv", ["stocks", "routine", "--date", "2026-08-18"]),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("ticker coverage is too low", stderr.getvalue())
        daily_summary.assert_not_called()

    def test_routine_reviews_before_persisting_current_picks(self) -> None:
        calls: list[str] = []

        def record(name: str, result: str):
            def side_effect(*args, **kwargs):
                calls.append(name)
                return result

            return side_effect

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch(
                "stock_expert.cli.ensure_bucketed_default_pilot",
                side_effect=record("initialize", {"status": "active"}),
                create=True,
            ),
            patch(
                "stock_expert.cli.import_daily_csv_command",
                return_value=json.dumps({"ok": True}),
            ),
            patch(
                "stock_expert.cli.daily_summary",
                side_effect=record("daily", "daily"),
            ),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch(
                "stock_expert.cli.review_output",
                side_effect=record("review", "review"),
            ),
            patch(
                "stock_expert.cli.picks_output",
                side_effect=record("picks", "picks"),
            ),
            patch(
                "stock_expert.cli.bucketed_strategy_comparison_output",
                return_value="comparison",
            ),
            patch("stock_expert.cli.downside_risk_output", return_value="downside"),
            patch("sys.argv", ["stocks", "routine", "--date", "2026-04-21"]),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            exit_code = cli.main()

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertLess(calls.index("initialize"), calls.index("review"))
        self.assertLess(calls.index("review"), calls.index("picks"))
        self.assertLess(output.index("Pick List:"), output.index("Review:"))

    def test_routine_uses_persisted_review(self) -> None:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch(
                "stock_expert.cli.ensure_bucketed_default_pilot",
                return_value={"status": "active"},
            ) as ensure_bucketed_default_pilot,
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
        ensure_bucketed_default_pilot.assert_called_once_with(
            self.settings,
            cli.date(2026, 4, 21),
        )
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
        self.assertNotIn("requested_date", output)

    def test_routine_resolves_non_session_date_to_previous_session(self) -> None:
        # 2026-11-07 is a Saturday; its data is Friday 2026-11-06's close.
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.ensure_bucketed_default_pilot") as ensure_bucketed_default_pilot,
            patch(
                "stock_expert.cli.import_daily_csv_command",
                return_value=json.dumps({"ok": True}),
            ) as csv_import,
            patch("stock_expert.cli.daily_summary", return_value="daily") as daily_summary,
            patch("stock_expert.cli.market_context_output", return_value="market") as market_context_output,
            patch("stock_expert.cli.picks_output", return_value="picks") as picks_output,
            patch("stock_expert.cli.bucketed_strategy_comparison_output", return_value="bucketed"),
            patch("stock_expert.cli.downside_risk_output", return_value="downside"),
            patch("stock_expert.cli.review_output", return_value="review") as review_output,
            patch("sys.argv", ["stocks", "routine", "--date", "2026-11-07"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = cli.main()

        friday = cli.date(2026, 11, 6)
        self.assertEqual(exit_code, 0)
        csv_import.assert_called_once_with(
            settings=self.settings,
            snapshot_date="2026-11-06",
            data_dir="data",
        )
        ensure_bucketed_default_pilot.assert_called_once_with(self.settings, friday)
        market_context_output.assert_called_once_with(friday)
        daily_summary.assert_called_once_with(self.settings, friday, ranking_context=ANY)
        review_output.assert_called_once_with(self.settings, friday, ranking_context=ANY)
        picks_output.assert_called_once_with(self.settings, friday, ranking_context=ANY)
        header = json.loads(stdout.getvalue().split("\n\n", 1)[0])
        self.assertEqual(header["routine_date"], "2026-11-06")
        self.assertEqual(header["requested_date"], "2026-11-07")
        self.assertIn("2026-11-07 is not an open trading session", stderr.getvalue())
        self.assertIn("resolves to 2026-11-06", stderr.getvalue())
        self.assertNotIn("calendar_warnings", header)

    def run_routine_header(self, requested: str) -> tuple[dict[str, object], str]:
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.ensure_bucketed_default_pilot"),
            patch("stock_expert.cli.import_daily_csv_command", return_value=json.dumps({"ok": True})),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.bucketed_strategy_comparison_output", return_value="bucketed"),
            patch("stock_expert.cli.downside_risk_output", return_value="downside"),
            patch("stock_expert.cli.review_output", return_value="review"),
            patch("sys.argv", ["stocks", "routine", "--date", requested]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(cli.main(), 0)
        return json.loads(stdout.getvalue().split("\n\n", 1)[0]), stderr.getvalue()

    def test_routine_header_warns_when_calendar_year_is_not_confirmed(self) -> None:
        for requested in ("2027-03-03", "2026-12-31"):
            with self.subTest(requested=requested):
                header, stderr = self.run_routine_header(requested)

                self.assertEqual(len(header["calendar_warnings"]), 1)
                self.assertIn("2027", header["calendar_warnings"][0])
                self.assertIn("routine: No confirmed variable-date BIST holidays are recorded for 2027", stderr)

    def test_routine_header_has_no_calendar_warning_for_confirmed_year(self) -> None:
        header, stderr = self.run_routine_header("2026-04-21")

        self.assertEqual(header, {"routine": "routine", "routine_date": "2026-04-21", "import": {"ok": True}})
        self.assertEqual(stderr, "")

    def test_routine_checks_review_evidence_for_the_resolved_date_before_importing(self) -> None:
        calls: list[str] = []
        self.check_review_evidence.side_effect = lambda *args, **kwargs: calls.append("check")

        def record_import(*args, **kwargs):
            calls.append("import")
            return json.dumps({"ok": True})

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.ensure_bucketed_default_pilot"),
            patch("stock_expert.cli.import_daily_csv_command", side_effect=record_import),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.bucketed_strategy_comparison_output", return_value="bucketed"),
            patch("stock_expert.cli.downside_risk_output", return_value="downside"),
            patch("stock_expert.cli.review_output", return_value="review"),
            patch("sys.argv", ["stocks", "routine", "--date", "2026-11-07"]),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(), 0)

        self.check_review_evidence.assert_called_once_with(self.settings, cli.date(2026, 11, 6))
        self.assertEqual(calls, ["check", "import"])

    def test_routine_reports_review_conflict_raised_during_review(self) -> None:
        conflict = ReviewEvidenceConflict(
            cli.date(2026, 4, 20),
            cli.date(2026, 4, 21),
            [{"id": 9, "as_of_date": "2026-04-17", "review_date": "2026-04-21"}],
        )
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("stock_expert.cli.ensure_bucketed_default_pilot"),
            patch("stock_expert.cli.import_daily_csv_command", return_value=json.dumps({"ok": True})),
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch("stock_expert.cli.picks_output", return_value="picks") as picks_output,
            patch("stock_expert.cli.review_output", side_effect=conflict),
            patch("sys.argv", ["stocks", "routine", "--date", "2026-04-21"]),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(cli.main(), 1)

        picks_output.assert_not_called()
        self.assertIn("routine: Refusing to persist review 2026-04-20 -> 2026-04-21", stderr.getvalue())


class CliReviewEvidenceGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent / ".test_tmp" / f"cli_guard_{uuid.uuid4().hex}"
        self.settings = Settings(
            base_dir=base_dir,
            data_dir=base_dir / "data",
            db_path=base_dir / "data" / "test.db",
        )
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.settings)
        self.addCleanup(shutil.rmtree, base_dir, ignore_errors=True)

    def _seed_review(self, signal_date: cli.date, review_date: cli.date) -> int:
        review_id, _ = persist_review_bundle(
            self.settings,
            as_of=signal_date,
            review_date=review_date,
            avg_return=0.02,
            win_rate=0.0,
            picks=[{"ticker": "CCC", "score": 1.0, "open_price": 100.0, "close_price": 102.0}],
            weights=Weights(date=review_date, momentum_weight=0.55, volume_weight=0.45),
            candidate_outcomes=[],
            signal_snapshot_id=None,
        )
        return review_id

    def _seed_signal_picks(self, signal_date: cli.date, review_date: cli.date) -> None:
        # Signal and review snapshots plus a persisted signal-date pick: enough
        # for a persisted review of the pair to write pick results.
        signal_snapshot_id = persist_daily_snapshot(
            self.settings,
            snapshot_date=signal_date,
            source_label="daily_csv",
            source_dir="data",
            market_rows=[],
            price_rows=[
                ("AAA", signal_date, 100.0, 101.0, 1_000_000),
                ("BBB", signal_date, 50.0, 51.0, 1_000_000),
            ],
        )
        persist_daily_snapshot(
            self.settings,
            snapshot_date=review_date,
            source_label="daily_csv",
            source_dir="data",
            market_rows=[],
            price_rows=[
                ("AAA", review_date, 101.0, 106.0, 1_000_000),
                ("BBB", review_date, 51.0, 50.0, 1_000_000),
            ],
        )
        replace_picks_for_date(
            self.settings,
            [PickRow(date=signal_date, ticker="AAA", score=1.0, momentum=0.9, volume=0.8, risk="high")],
            signal_date,
            snapshot_id=signal_snapshot_id,
        )

    def _row_counts(self) -> dict[str, int]:
        with connect(self.settings) as conn:
            return {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "snapshot_runs",
                    "picks",
                    "weights",
                    "review_runs",
                    "review_pick_results",
                    "candidate_outcomes",
                    "strategy_pilot_state",
                    "strategy_pilot_sessions",
                )
            }

    def test_review_command_refuses_conflicting_persisted_review(self) -> None:
        review_id = self._seed_review(cli.date(2026, 4, 23), cli.date(2026, 4, 24))
        before = self._row_counts()

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("sys.argv", ["stocks", "review", "--date", "2026-04-24"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(
            f"review: Refusing to persist review 2026-04-22 -> 2026-04-24: existing review {review_id} "
            "(2026-04-23 -> 2026-04-24) already covers review date 2026-04-24",
            stderr.getvalue(),
        )
        self.assertIn("Use review --date 2026-04-24 --dry-run to inspect.", stderr.getvalue())
        self.assertEqual(self._row_counts(), before)

    def test_review_command_dry_run_ignores_the_guard(self) -> None:
        self._seed_review(cli.date(2026, 4, 23), cli.date(2026, 4, 24))
        before = self._row_counts()

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("sys.argv", ["stocks", "review", "--date", "2026-04-24", "--dry-run"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        self.assertTrue(json.loads(stdout.getvalue())["dry_run"])
        self.assertEqual(self._row_counts(), before)

    def test_review_command_refuses_a_non_session_review_date(self) -> None:
        # 2026-11-14 is a Saturday. A snapshot stored under it would let an
        # unguarded review write a review row for the weekend.
        self._seed_signal_picks(cli.date(2026, 11, 13), cli.date(2026, 11, 14))
        before = self._row_counts()

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("sys.argv", ["stocks", "review", "--date", "2026-11-14"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(),
            "review: Refusing to persist a review for review date 2026-11-14: it is not an open trading session. "
            "Reviews are recorded only on trading sessions.\n",
        )
        self.assertEqual(self._row_counts(), before)

    def test_review_command_dry_run_runs_on_a_non_session_date(self) -> None:
        self._seed_signal_picks(cli.date(2026, 11, 13), cli.date(2026, 11, 14))
        before = self._row_counts()

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch("sys.argv", ["stocks", "review", "--date", "2026-11-14", "--dry-run"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["signal_date"], "2026-11-13")
        self.assertEqual(payload["review_date"], "2026-11-14")
        self.assertEqual(self._row_counts(), before)

    def test_saturday_routine_passes_the_guard_for_the_resolved_friday(self) -> None:
        # The routine resolves 2026-11-07 (Saturday) to Friday 2026-11-06
        # before the guard runs, so the non-session refusal never applies.
        friday = cli.date(2026, 11, 6)
        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch(
                "stock_expert.cli.check_review_evidence",
                wraps=services.check_review_evidence,
            ) as check_review_evidence,
            patch("stock_expert.cli.ensure_bucketed_default_pilot"),
            patch(
                "stock_expert.cli.import_daily_csv_command",
                return_value=json.dumps({"ok": True}),
            ) as csv_import,
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.bucketed_strategy_comparison_output", return_value="bucketed"),
            patch("stock_expert.cli.downside_risk_output", return_value="downside"),
            patch("stock_expert.cli.review_output", return_value="review") as review_output,
            patch("sys.argv", ["stocks", "routine", "--date", "2026-11-07"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        check_review_evidence.assert_called_once_with(self.settings, friday)
        csv_import.assert_called_once_with(settings=self.settings, snapshot_date="2026-11-06", data_dir="data")
        review_output.assert_called_once_with(self.settings, friday, ranking_context=ANY)
        self.assertNotIn("Refusing", stderr.getvalue())
        self.assertEqual(json.loads(stdout.getvalue().split("\n\n", 1)[0])["routine_date"], "2026-11-06")

    def test_routine_refuses_conflicting_review_before_importing(self) -> None:
        # Review 136 (2026-11-06 -> 2026-11-07, a Saturday) is stored. The
        # Friday picks and the Monday snapshot are stored as well, so a routine
        # for 2026-11-09 that got past the guard would persist a second review
        # of the Friday basket through the real review_output.
        self._seed_signal_picks(cli.date(2026, 11, 6), cli.date(2026, 11, 9))
        self._seed_review(cli.date(2026, 11, 6), cli.date(2026, 11, 7))
        before = self._row_counts()

        with (
            patch("stock_expert.cli.get_settings", return_value=self.settings),
            patch(
                "stock_expert.cli.import_daily_csv_command",
                return_value=json.dumps({"ok": True}),
            ) as csv_import,
            patch(
                "stock_expert.cli.ensure_bucketed_default_pilot",
                wraps=services.ensure_bucketed_default_pilot,
            ) as ensure_pilot,
            patch("stock_expert.cli.daily_summary", return_value="daily"),
            patch("stock_expert.cli.market_context_output", return_value="market"),
            patch("stock_expert.cli.picks_output", return_value="picks"),
            patch("stock_expert.cli.bucketed_strategy_comparison_output", return_value="bucketed"),
            patch("stock_expert.cli.downside_risk_output", return_value="downside"),
            patch("stock_expert.cli.review_output", wraps=services.review_output) as review_output,
            patch("sys.argv", ["stocks", "routine", "--date", "2026-11-09"]),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        csv_import.assert_not_called()
        ensure_pilot.assert_not_called()
        review_output.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("routine: Refusing to persist review 2026-11-06 -> 2026-11-09", stderr.getvalue())
        self.assertEqual(self._row_counts(), before)


if __name__ == "__main__":
    unittest.main()
