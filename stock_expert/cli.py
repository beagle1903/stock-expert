from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from stock_expert.config import get_settings
from stock_expert.daily_csv import DailyCsvError, import_daily_csv_command, import_daily_csv_folder_command
from stock_expert.investing_csv import (
    InvestingCsvError,
    publish_uploaded_csvs_command,
    refresh_investing_csvs_command,
)
from stock_expert.services import (
    RankingContext,
    bucketed_strategy_comparison_output,
    daily_summary,
    downside_risk_output,
    ensure_bucketed_default_pilot,
    market_context_output,
    picks_output,
    review_output,
)
from stock_expert.yahoo import download_ohlcv_command, import_ohlcv_excel_command
from stock_expert.workspace_bundle import (
    WorkspaceBundleError,
    export_workspace_bundle,
    import_workspace_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stocks", description="BIST intraday stock advisor MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in ("daily", "picks", "review"):
        command_parser = subparsers.add_parser(command_name)
        command_parser.add_argument(
            "--date",
            dest="as_of",
            default=date.today().isoformat(),
            help="As-of date in YYYY-MM-DD format",
        )
        if command_name in {"picks", "review"}:
            command_parser.add_argument(
                "--dry-run",
                action="store_true",
                help="Compute output without writing picks, signals, weights, or review rows",
            )

    download_parser = subparsers.add_parser("download-ohlcv", help="Download OHLCV history from Yahoo Finance")
    download_parser.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="One or more BIST tickers, with or without the .IS suffix",
    )
    download_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of calendar days to download, default is 30",
    )
    download_parser.add_argument(
        "--output",
        default="data/yahoo_ohlcv.csv",
        help="CSV output path relative to the project root",
    )
    download_parser.add_argument(
        "--import-db",
        action="store_true",
        help="Also import ticker, date, open_price, close_price, volume into SQLite",
    )
    download_parser.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
        help="Pause between ticker requests, default is 1.0 second",
    )
    download_parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="Maximum retry attempts per ticker on rate limiting or transient errors",
    )
    bulk_parser = subparsers.add_parser("import-ohlcv-excel", help="Bulk import Yahoo OHLCV using ticker codes from an Excel workbook")
    bulk_parser.add_argument("--input", default="data/sirketler.xlsx", help="Excel input path relative to the project root")
    bulk_parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD format")
    bulk_parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD format")
    bulk_parser.add_argument("--pause-seconds", type=float, default=1.5, help="Pause between ticker requests")
    bulk_parser.add_argument("--max-retries", type=int, default=5, help="Max retries per ticker")
    bulk_parser.add_argument("--batch-size", type=int, default=25, help="Pause after each batch of tickers")
    bulk_parser.add_argument("--batch-pause-seconds", type=float, default=20.0, help="Pause between batches")
    csv_parser = subparsers.add_parser("import-daily-csv", help="Import daily snapshot CSV files from the data folder")
    csv_parser.add_argument("--date", dest="as_of", required=True, help="Snapshot date in YYYY-MM-DD format")
    csv_parser.add_argument("--data-dir", default="data", help="Directory containing fiyat/performans/teknik/temel csv files")
    refresh_parser = subparsers.add_parser(
        "refresh-investing-csvs",
        help="Refresh the four live CSV files from the rendered Investing.com Türkiye stock tables",
    )
    refresh_parser.add_argument("--data-dir", default="data", help="Destination directory for the four CSV files")
    refresh_parser.add_argument("--min-rows", type=int, default=500, help="Minimum rows required in every table")
    refresh_parser.add_argument(
        "--max-more-clicks",
        type=int,
        default=12,
        help="Safety limit for Daha Fazla clicks on each tab",
    )
    refresh_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Maximum browser wait, including time for a user-completed access challenge",
    )
    refresh_parser.add_argument("--browser", help="Optional Edge or Chrome executable path")
    refresh_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without a visible browser; visible mode is more reliable for access challenges",
    )
    upload_parser = subparsers.add_parser(
        "publish-investing-csvs",
        help="Validate and atomically publish an uploaded four-file Investing.com CSV bundle",
    )
    upload_parser.add_argument(
        "--source-dir",
        required=True,
        help="Directory containing the uploaded fiyat/performans/teknik/temel CSV files",
    )
    upload_parser.add_argument("--data-dir", default="data", help="Destination directory for the four CSV files")
    upload_parser.add_argument("--min-rows", type=int, default=500, help="Minimum rows required in every table")
    export_parser = subparsers.add_parser(
        "export-workspace-bundle",
        help="Create a portable SQLite and live-CSV bundle for another workspace",
    )
    export_parser.add_argument(
        "--output",
        default="data/backups/stock_expert_workspace.zip",
        help="Output ZIP path relative to the project root",
    )
    export_parser.add_argument("--data-dir", default="data", help="Directory containing the four live CSV files")
    export_parser.add_argument("--min-rows", type=int, default=500, help="Minimum rows required in every table")
    export_parser.add_argument(
        "--without-inputs",
        action="store_true",
        help="Export SQLite history only, without the four live CSV files",
    )
    import_parser = subparsers.add_parser(
        "import-workspace-bundle",
        help="Validate and restore a portable SQLite and live-CSV workspace bundle",
    )
    import_parser.add_argument("--input", required=True, help="Input ZIP path relative to the project root")
    import_parser.add_argument("--data-dir", default="data", help="Destination directory for the four CSV files")
    import_parser.add_argument("--min-rows", type=int, default=500, help="Minimum rows required in every table")
    import_parser.add_argument(
        "--replace-database",
        action="store_true",
        help="Replace an existing active database after creating a local backup",
    )
    folder_parser = subparsers.add_parser("import-daily-folder", help="Import a dated folder containing the four daily CSV files")
    folder_parser.add_argument("--folder", required=True, help="Folder path relative to the project root, e.g. data/20260408")
    routine_parser = subparsers.add_parser(
        "routine",
        help="Import live CSV files, summarize market, run persisted picks/review, and report diagnostics",
    )
    routine_parser.add_argument(
        "--date",
        dest="as_of",
        default=date.today().isoformat(),
        help="Snapshot date in YYYY-MM-DD format, default is today",
    )
    routine_parser.add_argument("--data-dir", default="data", help="Directory containing the four live csv files")
    midday_parser = subparsers.add_parser(
        "midday-routine",
        help="Import live CSV files, summarize market, generate picks, and run dry-run review",
    )
    midday_parser.add_argument(
        "--date",
        dest="as_of",
        default=date.today().isoformat(),
        help="Snapshot date in YYYY-MM-DD format, default is today",
    )
    midday_parser.add_argument("--data-dir", default="data", help="Directory containing the four live csv files")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()

    if args.command == "daily":
        as_of = date.fromisoformat(args.as_of)
        print(daily_summary(settings, as_of))
        return 0
    if args.command == "picks":
        as_of = date.fromisoformat(args.as_of)
        print(
            picks_output(
                settings,
                as_of,
                dry_run=args.dry_run,
            )
        )
        return 0
    if args.command == "review":
        as_of = date.fromisoformat(args.as_of)
        print(
            review_output(
                settings,
                as_of,
                dry_run=args.dry_run,
            )
        )
        return 0
    if args.command == "download-ohlcv":
        print(
            download_ohlcv_command(
                settings=settings,
                tickers=args.tickers,
                days=args.days,
                output_path=args.output,
                import_db=args.import_db,
                pause_seconds=args.pause_seconds,
                max_retries=args.max_retries,
            )
        )
        return 0
    if args.command == "import-ohlcv-excel":
        print(
            import_ohlcv_excel_command(
                settings=settings,
                input_path=args.input,
                start_date=args.start_date,
                end_date=args.end_date,
                pause_seconds=args.pause_seconds,
                max_retries=args.max_retries,
                batch_size=args.batch_size,
                batch_pause_seconds=args.batch_pause_seconds,
            )
        )
        return 0
    if args.command == "import-daily-csv":
        try:
            print(import_daily_csv_command(settings=settings, snapshot_date=args.as_of, data_dir=args.data_dir))
        except DailyCsvError as exc:
            print(f"import-daily-csv: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "refresh-investing-csvs":
        try:
            print(
                refresh_investing_csvs_command(
                    settings=settings,
                    data_dir=args.data_dir,
                    min_rows=args.min_rows,
                    max_more_clicks=args.max_more_clicks,
                    timeout_seconds=args.timeout_seconds,
                    browser_path=args.browser,
                    headless=args.headless,
                )
            )
        except (InvestingCsvError, ValueError) as exc:
            print(f"refresh-investing-csvs: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "publish-investing-csvs":
        try:
            print(
                publish_uploaded_csvs_command(
                    settings=settings,
                    source_dir=args.source_dir,
                    data_dir=args.data_dir,
                    min_rows=args.min_rows,
                )
            )
        except (InvestingCsvError, ValueError) as exc:
            print(f"publish-investing-csvs: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "export-workspace-bundle":
        try:
            print(
                json.dumps(
                    export_workspace_bundle(
                        settings=settings,
                        output_path=args.output,
                        data_dir=args.data_dir,
                        include_inputs=not args.without_inputs,
                        min_rows=args.min_rows,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except (WorkspaceBundleError, InvestingCsvError, ValueError) as exc:
            print(f"export-workspace-bundle: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "import-workspace-bundle":
        try:
            print(
                json.dumps(
                    import_workspace_bundle(
                        settings=settings,
                        input_path=args.input,
                        data_dir=args.data_dir,
                        replace_database=args.replace_database,
                        min_rows=args.min_rows,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except (WorkspaceBundleError, InvestingCsvError, ValueError) as exc:
            print(f"import-workspace-bundle: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "import-daily-folder":
        try:
            print(import_daily_csv_folder_command(settings=settings, folder=args.folder))
        except DailyCsvError as exc:
            print(f"import-daily-folder: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command in {"routine", "midday-routine"}:
        as_of = date.fromisoformat(args.as_of)
        ranking_context = RankingContext()
        try:
            import_result = json.loads(
                import_daily_csv_command(settings=settings, snapshot_date=args.as_of, data_dir=args.data_dir)
            )
        except DailyCsvError as exc:
            print(f"{args.command}: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {"routine": args.command, "routine_date": args.as_of, "import": import_result},
                indent=2,
            )
        )
        print()
        print("Market Context:")
        print(market_context_output(as_of))
        print()
        if args.command == "routine":
            ensure_bucketed_default_pilot(settings, as_of)
        daily_output = daily_summary(
            settings,
            as_of,
            ranking_context=ranking_context,
        )
        if args.command == "midday-routine":
            pick_list_output = picks_output(
                settings,
                as_of,
                ranking_context=ranking_context,
            )
            persisted_review_output = None
            dry_run_review_output = review_output(
                settings,
                as_of,
                dry_run=True,
                ranking_context=ranking_context,
            )
        else:
            persisted_review_output = review_output(
                settings,
                as_of,
                ranking_context=ranking_context,
            )
            pick_list_output = picks_output(
                settings,
                as_of,
                ranking_context=ranking_context,
            )
            dry_run_review_output = None
        print(daily_output)
        print()
        print("Pick List:")
        print(pick_list_output)
        print()
        if args.command == "midday-routine":
            print("Dry-Run Review:")
            print(dry_run_review_output)
        else:
            print("Review:")
            print(persisted_review_output)
            print()
            print("Score-Ranked vs Bucketed Review Comparison:")
            print(
                bucketed_strategy_comparison_output(
                    settings,
                    as_of,
                    ranking_context=ranking_context,
                )
            )
            print()
            print("Downside Risk Diagnostic:")
            print(downside_risk_output(settings, as_of, ranking_context=ranking_context))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
