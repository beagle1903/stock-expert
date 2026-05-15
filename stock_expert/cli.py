from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from stock_expert.config import get_settings
from stock_expert.daily_csv import import_daily_csv_command, import_daily_csv_folder_command
from stock_expert.services import (
    bucketed_strategy_comparison_output,
    daily_summary,
    pick_disagreement_output,
    picks_output,
    review_output,
)
from stock_expert.yahoo import download_ohlcv_command, import_ohlcv_excel_command


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
            command_parser.add_argument(
                "--no-chase-penalty",
                action="store_true",
                help="Disable the same-day overextension penalty for comparison",
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
    folder_parser = subparsers.add_parser("import-daily-folder", help="Import a dated folder containing the four daily CSV files")
    folder_parser.add_argument("--folder", required=True, help="Folder path relative to the project root, e.g. data/20260408")
    routine_parser = subparsers.add_parser(
        "routine",
        help="Import live CSV files, summarize market, run persisted picks/review, and report no-chase dry-run comparisons",
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
                apply_chase_penalty=not args.no_chase_penalty,
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
                apply_chase_penalty=not args.no_chase_penalty,
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
        print(import_daily_csv_command(settings=settings, snapshot_date=args.as_of, data_dir=args.data_dir))
        return 0
    if args.command == "import-daily-folder":
        print(import_daily_csv_folder_command(settings=settings, folder=args.folder))
        return 0
    if args.command in {"routine", "midday-routine"}:
        as_of = date.fromisoformat(args.as_of)
        import_result = json.loads(
            import_daily_csv_command(settings=settings, snapshot_date=args.as_of, data_dir=args.data_dir)
        )
        print(
            json.dumps(
                {"routine": args.command, "routine_date": args.as_of, "import": import_result},
                indent=2,
            )
        )
        print()
        print(daily_summary(settings, as_of))
        print()
        print(picks_output(settings, as_of))
        print()
        if args.command == "midday-routine":
            print("Dry-Run Review:")
            print(review_output(settings, as_of, dry_run=True))
        else:
            print("Review:")
            print(review_output(settings, as_of))
            print()
            print("Score-Ranked vs Bucketed Review Comparison:")
            print(bucketed_strategy_comparison_output(settings, as_of))
            print()
            print("Normal vs No-Chase Disagreement:")
            print(pick_disagreement_output(settings, as_of))
            print()
            print("No-Chase Dry-Run Picks:")
            print(picks_output(settings, as_of, dry_run=True, apply_chase_penalty=False))
            print()
            print("No-Chase Dry-Run Review:")
            print(review_output(settings, as_of, dry_run=True, apply_chase_penalty=False))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
