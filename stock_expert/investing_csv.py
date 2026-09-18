from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from stock_expert.config import Settings
from stock_expert.daily_csv import SOURCE_SYMBOL_HEADERS, _normalize_source_symbol


SOURCE_URL = "https://tr.investing.com/equities/turkey"
CSV_HEADERS = {
    "fiyat.csv": ["İsim", "Son", " Yüksek", " Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
    "performans.csv": ["İsim", "Günlük", "Haftalık", " 1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
    "teknik.csv": ["İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
    "temel.csv": [
        "İsim",
        "Ortalama Hacim (3Ay)",
        "Piyasa değeri",
        "Gelir",
        "Fiyat / Kazanç Oranı",
        "Beta",
    ],
}

HEADER_TRANSLATION = str.maketrans(
    {
        "İ": "I",
        "ı": "I",
        "Ş": "S",
        "ş": "S",
        "Ğ": "G",
        "ğ": "G",
        "Ü": "U",
        "ü": "U",
        "Ö": "O",
        "ö": "O",
        "Ç": "C",
        "ç": "C",
    }
)


class InvestingCsvError(RuntimeError):
    """Raised when the browser extraction cannot safely publish a CSV bundle."""


def _normalize_header(value: str) -> str:
    translated = value.translate(HEADER_TRANSLATION).upper()
    return "".join(character for character in translated if character.isalnum())


def _header_mismatch_error(filename: str, expected_headers: list[str], source_headers: list[str]) -> InvestingCsvError:
    return InvestingCsvError(
        f"{filename} header mismatch: expected {expected_headers}, received {source_headers}"
    )


def _match_table_headers(
    filename: str, source_headers: list[str], expected_headers: list[str]
) -> tuple[int, int | None]:
    normalized_source = [_normalize_header(value) for value in source_headers]
    normalized_expected = [_normalize_header(value) for value in expected_headers]
    if normalized_source == normalized_expected:
        return 0, None
    if len(normalized_source) == len(normalized_expected) + 1:
        if normalized_source[0] in SOURCE_SYMBOL_HEADERS and normalized_source[1:] == normalized_expected:
            return 1, 0
        if (
            normalized_source[0] == normalized_expected[0]
            and normalized_source[1] in SOURCE_SYMBOL_HEADERS
            and normalized_source[2:] == normalized_expected[1:]
        ):
            return 0, 1
    raise _header_mismatch_error(filename, expected_headers, source_headers)


def _published_headers(
    source_headers: list[str], expected_headers: list[str], symbol_index: int | None
) -> list[str]:
    if symbol_index is None:
        return expected_headers
    published = list(expected_headers)
    published.insert(symbol_index, source_headers[symbol_index])
    return published


def validate_extracted_tables(payload: dict[str, Any], min_rows: int) -> dict[str, int]:
    if min_rows < 1:
        raise ValueError("min_rows must be at least 1")

    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise InvestingCsvError("Browser output does not contain a tables object")

    row_counts: dict[str, int] = {}
    company_sets: dict[str, Counter[str]] = {}
    company_symbols: dict[str, set[str]] = {}

    for filename, expected_headers in CSV_HEADERS.items():
        table = tables.get(filename)
        if not isinstance(table, dict):
            raise InvestingCsvError(f"Browser output is missing {filename}")

        source_headers = table.get("headers")
        rows = table.get("rows")
        if not isinstance(source_headers, list) or not all(isinstance(value, str) for value in source_headers):
            raise InvestingCsvError(f"{filename} headers are invalid")
        if not isinstance(rows, list):
            raise InvestingCsvError(f"{filename} rows are invalid")

        isim_index, symbol_index = _match_table_headers(filename, source_headers, expected_headers)
        if len(rows) < min_rows:
            raise InvestingCsvError(
                f"{filename} has {len(rows)} rows; at least {min_rows} are required before publication"
            )

        companies: list[str] = []
        for row_number, row in enumerate(rows, start=2):
            if not isinstance(row, list) or len(row) != len(source_headers):
                raise InvestingCsvError(
                    f"{filename} row {row_number} has {len(row) if isinstance(row, list) else 'invalid'} "
                    f"columns; expected {len(source_headers)}"
                )
            if not all(isinstance(value, str) for value in row):
                raise InvestingCsvError(f"{filename} row {row_number} contains a non-text value")
            company_name = row[isim_index].strip()
            if not company_name:
                raise InvestingCsvError(f"{filename} row {row_number} has an empty company name")
            companies.append(company_name)
            if symbol_index is not None:
                normalized_symbol = _normalize_source_symbol(row[symbol_index])
                if normalized_symbol:
                    company_symbols.setdefault(company_name, set()).add(normalized_symbol)

        row_counts[filename] = len(rows)
        company_sets[filename] = Counter(companies)

    reference_file = next(iter(CSV_HEADERS))
    reference_companies = company_sets[reference_file]
    for filename, companies in company_sets.items():
        if companies != reference_companies:
            missing = list((reference_companies - companies).elements())[:5]
            extra = list((companies - reference_companies).elements())[:5]
            raise InvestingCsvError(
                f"{filename} company coverage differs from {reference_file}; "
                f"missing={missing}, extra={extra}"
            )

    conflicts = [name for name, symbols in company_symbols.items() if len(symbols) > 1]
    if conflicts:
        raise InvestingCsvError(f"symbol conflict for companies: {conflicts[:5]}")

    return row_counts


def publish_extracted_tables(payload: dict[str, Any], destination: Path, min_rows: int) -> dict[str, int]:
    row_counts = validate_extracted_tables(payload, min_rows=min_rows)
    destination.mkdir(parents=True, exist_ok=True)
    transaction_id = uuid.uuid4().hex
    staging = destination / f".investing-stage-{transaction_id}"
    staging.mkdir()
    backups: dict[Path, Path] = {}
    published: list[Path] = []

    try:
        for filename, headers in CSV_HEADERS.items():
            source_headers = payload["tables"][filename]["headers"]
            _, symbol_index = _match_table_headers(filename, source_headers, headers)
            staged_file = staging / filename
            with staged_file.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
                writer.writerow(_published_headers(source_headers, headers, symbol_index))
                writer.writerows(payload["tables"][filename]["rows"])
                handle.flush()
                os.fsync(handle.fileno())

        for filename in CSV_HEADERS:
            target = destination / filename
            if target.exists():
                backup = staging / f"{filename}.backup"
                shutil.copy2(target, backup)
                backups[target] = backup
            os.replace(staging / filename, target)
            published.append(target)
    except Exception:
        for target in reversed(published):
            backup = backups.get(target)
            if backup and backup.exists():
                os.replace(backup, target)
            elif target.exists():
                target.unlink()
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return row_counts


def refresh_investing_csvs_command(
    settings: Settings,
    data_dir: str = "data",
    min_rows: int = 500,
    max_more_clicks: int = 12,
    timeout_seconds: int = 180,
    browser_path: str | None = None,
    headless: bool = False,
) -> str:
    if max_more_clicks < 1:
        raise ValueError("max_more_clicks must be at least 1")
    if timeout_seconds < 30:
        raise ValueError("timeout_seconds must be at least 30")

    node_path = shutil.which("node")
    if not node_path:
        raise InvestingCsvError("Node.js is required for browser extraction but was not found on PATH")

    base_dir = Path(settings.base_dir)
    destination = base_dir / data_dir
    script_path = base_dir / "scripts" / "investing_csv_extract.mjs"
    if not script_path.exists():
        raise InvestingCsvError(f"Browser extractor is missing: {script_path}")

    temp_root = base_dir / ".test_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    run_dir = temp_root / f"investing-csv-{uuid.uuid4().hex}"
    run_dir.mkdir()
    output_path = run_dir / "tables.json"
    profile_dir = Path(settings.data_dir) / ".investing-browser-profile"

    command = [
        node_path,
        str(script_path),
        "--url",
        SOURCE_URL,
        "--output",
        str(output_path),
        "--profile-dir",
        str(profile_dir),
        "--min-rows",
        str(min_rows),
        "--max-more-clicks",
        str(max_more_clicks),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if browser_path:
        command.extend(["--browser", browser_path])
    if headless:
        command.append("--headless")

    try:
        completed = subprocess.run(
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds + 45,
            check=False,
        )
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "unknown browser error").strip()
            raise InvestingCsvError(f"Investing.com browser extraction failed: {details[-3000:]}")
        if not output_path.exists():
            raise InvestingCsvError("Browser extraction completed without producing table data")

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        row_counts = publish_extracted_tables(payload, destination=destination, min_rows=min_rows)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

    return json.dumps(
        {
            "source_url": payload.get("source_url", SOURCE_URL),
            "selected_country": payload.get("selected_country"),
            "selected_market": payload.get("selected_market"),
            "more_clicks": payload.get("more_clicks", {}),
            "rows": row_counts,
            "files": [str(destination / filename) for filename in CSV_HEADERS],
        },
        ensure_ascii=False,
        indent=2,
    )
