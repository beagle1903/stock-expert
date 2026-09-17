from __future__ import annotations

import csv
import json
import random
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zipfile

from stock_expert.config import Settings
from stock_expert.database import init_db, persist_yahoo_prices


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LIVE_CSV_NAMES = frozenset({"fiyat.csv", "performans.csv", "teknik.csv", "temel.csv"})


class YahooChartError(ValueError):
    pass


def _cell_text(cell: ET.Element) -> str:
    if cell is None:
        return ""
    return "".join(cell.itertext()).strip()


def normalize_yahoo_symbol(ticker: str) -> tuple[str, str]:
    clean = ticker.strip().upper()
    if clean.endswith(".IS"):
        local = clean[:-3]
        yahoo = clean
    else:
        local = clean
        yahoo = f"{clean}.IS"
    if not local.isalnum() or not (1 <= len(local) <= 8):
        raise ValueError(f"invalid ticker: {ticker}")
    return yahoo, local


def resolve_yahoo_output_path(settings: Settings, output_path: str) -> Path:
    data_root = (settings.base_dir / "data").resolve()
    candidate = (settings.base_dir / output_path).resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("Yahoo output path must stay under data/") from exc
    if candidate.name.lower() in LIVE_CSV_NAMES:
        raise ValueError(f"Yahoo output cannot replace live CSV {candidate.name}")
    return candidate


def _chart_window(
    days: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[datetime, datetime]:
    if start_date is not None and end_date is not None:
        period_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC) - timedelta(days=5)
        period_end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC) + timedelta(days=1)
        return period_start, period_end
    if days is None:
        raise ValueError("days or start_date and end_date are required")
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days + 5)
    return period_start, period_end


def _parse_yahoo_chart(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise YahooChartError("malformed Yahoo chart payload")
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise YahooChartError("malformed Yahoo chart payload")
    error = chart.get("error")
    if error:
        description = error.get("description") if isinstance(error, dict) else str(error)
        raise YahooChartError(description or "Yahoo chart error")
    result = chart.get("result")
    if not result:
        raise YahooChartError("empty Yahoo chart result")
    first = result[0]
    try:
        timestamps = first.get("timestamp") or []
        quote_rows = first["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise YahooChartError("malformed Yahoo chart payload") from exc
    rows: list[dict[str, object]] = []
    for idx, timestamp in enumerate(timestamps):
        open_price = quote_rows["open"][idx]
        high_price = quote_rows["high"][idx]
        low_price = quote_rows["low"][idx]
        close_price = quote_rows["close"][idx]
        volume = quote_rows["volume"][idx]
        if None in (open_price, high_price, low_price, close_price, volume):
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, UTC).date().isoformat(),
                "open": round(float(open_price), 4),
                "high": round(float(high_price), 4),
                "low": round(float(low_price), 4),
                "close": round(float(close_price), 4),
                "volume": int(volume),
            }
        )
    return rows


def fetch_yahoo_ohlcv(
    symbol: str,
    days: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    period_start, period_end = _chart_window(days=days, start_date=start_date, end_date=end_date)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
        f"?period1={int(period_start.timestamp())}"
        f"&period2={int(period_end.timestamp())}"
        "&interval=1d&includePrePost=false&events=div%2Csplits"
    )
    with urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _parse_yahoo_chart(payload)


def fetch_yahoo_ohlcv_with_retry(
    symbol: str,
    days: int | None = None,
    max_retries: int = 0,
    pause_seconds: float = 1.0,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, object]]:
    attempt = 0
    while True:
        try:
            return fetch_yahoo_ohlcv(symbol, days=days, start_date=start_date, end_date=end_date)
        except HTTPError as exc:
            if exc.code != 429 or attempt >= max_retries:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            base_delay = float(retry_after) if retry_after else pause_seconds * (2 ** attempt)
            delay = base_delay + random.uniform(0, pause_seconds)
            print(
                f"[download-ohlcv] {symbol}: received HTTP 429, retry {attempt + 1}/{max_retries} in {delay:.1f}s"
            )
            time.sleep(delay)
            attempt += 1
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt >= max_retries:
                raise
            delay = pause_seconds * (2 ** attempt) + random.uniform(0, pause_seconds)
            print(
                f"[download-ohlcv] {symbol}: transient error '{exc}', retry {attempt + 1}/{max_retries} in {delay:.1f}s"
            )
            time.sleep(delay)
            attempt += 1


def load_tickers_from_excel(workbook_path: Path) -> list[str]:
    with zipfile.ZipFile(workbook_path) as zf:
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        tickers: list[str] = []
        seen: set[str] = set()
        for row in sheet.findall(".//x:sheetData/x:row", NS):
            values = [_cell_text(cell) for cell in row.findall("x:c", NS)]
            if not values:
                continue
            code = "".join(ch for ch in values[0].strip().upper() if ch.isalnum())
            if not code or code in {"KOD", "A"} or len(code) > 8:
                continue
            if code not in seen:
                seen.add(code)
                tickers.append(code)
    return tickers


def write_ohlcv_csv(output_file: Path, rows: Iterable[dict[str, object]]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "yahoo_symbol", "date", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _append_history_rows(
    history: list[dict[str, object]],
    local_ticker: str,
    yahoo_symbol: str,
    csv_rows: list[dict[str, object]],
    db_rows: list[tuple[str, date, float, float, float]],
    start: date | None = None,
    end: date | None = None,
) -> int:
    kept = 0
    for row in history:
        row_date = datetime.fromisoformat(str(row["date"])).date()
        if start is not None and row_date < start:
            continue
        if end is not None and row_date > end:
            continue
        csv_rows.append(
            {
                "ticker": local_ticker,
                "yahoo_symbol": yahoo_symbol,
                "date": row["date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
        )
        db_rows.append(
            (
                local_ticker,
                row_date,
                float(row["open"]),
                float(row["close"]),
                float(row["volume"]),
            )
        )
        kept += 1
    return kept


def _yahoo_source_dir(settings: Settings, output_file: Path) -> str:
    data_root = (settings.base_dir / "data").resolve()
    return "data/" + str(output_file.relative_to(data_root)).replace("\\", "/")


def _publish_yahoo_results(
    settings: Settings,
    output_file: Path,
    csv_rows: list[dict[str, object]],
    db_rows: list[tuple[str, date, float, float, float]],
    failures: list[dict[str, str]],
    import_db: bool,
) -> tuple[bool, int]:
    preserved_existing_output = False
    incomplete = bool(failures)
    if csv_rows and not (incomplete and output_file.exists()):
        write_ohlcv_csv(output_file, csv_rows)
    elif output_file.exists() and (incomplete or not csv_rows):
        preserved_existing_output = True
    imported_rows = 0
    if import_db and db_rows and not preserved_existing_output:
        init_db(settings)
        persist_yahoo_prices(settings, db_rows, source_dir=_yahoo_source_dir(settings, output_file))
        imported_rows = len(db_rows)
    return preserved_existing_output, imported_rows


def download_ohlcv_command(
    settings: Settings,
    tickers: list[str],
    days: int,
    output_path: str,
    import_db: bool,
    pause_seconds: float,
    max_retries: int,
) -> str:
    output_file = resolve_yahoo_output_path(settings, output_path)
    csv_rows: list[dict[str, object]] = []
    db_rows: list[tuple[str, date, float, float, float]] = []
    failures: list[dict[str, str]] = []

    total = len(tickers)
    for index, raw_ticker in enumerate(tickers, start=1):
        try:
            yahoo_symbol, local_ticker = normalize_yahoo_symbol(raw_ticker)
        except ValueError as exc:
            print(f"[download-ohlcv] ({index}/{total}) skipped {raw_ticker}: {exc}")
            failures.append({"ticker": raw_ticker, "error": str(exc)})
            continue
        print(f"[download-ohlcv] ({index}/{total}) fetching {yahoo_symbol}")
        try:
            history = fetch_yahoo_ohlcv_with_retry(
                yahoo_symbol,
                days=days,
                max_retries=max_retries,
                pause_seconds=pause_seconds,
            )
        except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, YahooChartError) as exc:
            print(f"[download-ohlcv] ({index}/{total}) failed {yahoo_symbol}: {exc}")
            failures.append({"ticker": raw_ticker, "error": str(exc)})
            continue
        print(f"[download-ohlcv] ({index}/{total}) fetched {yahoo_symbol}: {len(history)} rows")
        _append_history_rows(history, local_ticker, yahoo_symbol, csv_rows, db_rows)
        if index < total:
            print(f"[download-ohlcv] waiting {pause_seconds:.1f}s before next ticker")
            time.sleep(pause_seconds)

    csv_rows.sort(key=lambda item: (str(item["ticker"]), str(item["date"])))
    preserved_existing_output, imported_rows = _publish_yahoo_results(
        settings, output_file, csv_rows, db_rows, failures, import_db=import_db
    )

    return json.dumps(
        {
            "output_file": str(output_file),
            "requested_tickers": tickers,
            "downloaded_tickers": sorted({str(row["ticker"]) for row in csv_rows}),
            "rows_written": len(csv_rows),
            "rows_imported": imported_rows,
            "preserved_existing_output": preserved_existing_output,
            "pause_seconds": pause_seconds,
            "max_retries": max_retries,
            "failures": failures,
        },
        indent=2,
    )


def import_ohlcv_excel_command(
    settings: Settings,
    input_path: str,
    start_date: str,
    end_date: str,
    pause_seconds: float,
    max_retries: int,
    batch_size: int,
    batch_pause_seconds: float,
) -> str:
    workbook_path = settings.base_dir / input_path
    tickers = load_tickers_from_excel(workbook_path)
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    csv_rows: list[dict[str, object]] = []
    db_rows: list[tuple[str, date, float, float, float]] = []
    failures: list[dict[str, str]] = []
    total = len(tickers)
    output_file = resolve_yahoo_output_path(settings, "data/yahoo_ohlcv.csv")

    for index, raw_ticker in enumerate(tickers, start=1):
        yahoo_symbol, local_ticker = normalize_yahoo_symbol(raw_ticker)
        print(f"[bulk-ohlcv] ({index}/{total}) fetching {yahoo_symbol}")
        try:
            history = fetch_yahoo_ohlcv_with_retry(
                yahoo_symbol,
                max_retries=max_retries,
                pause_seconds=pause_seconds,
                start_date=start,
                end_date=end,
            )
        except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, YahooChartError) as exc:
            print(f"[bulk-ohlcv] ({index}/{total}) failed {yahoo_symbol}: {exc}")
            failures.append({"ticker": raw_ticker, "error": str(exc)})
            continue
        kept = _append_history_rows(history, local_ticker, yahoo_symbol, csv_rows, db_rows, start=start, end=end)
        print(f"[bulk-ohlcv] ({index}/{total}) kept {kept} rows")
        if index < total:
            time.sleep(pause_seconds)
        if batch_size > 0 and index % batch_size == 0 and index < total:
            print(f"[bulk-ohlcv] batch pause {batch_pause_seconds:.1f}s")
            time.sleep(batch_pause_seconds)

    csv_rows.sort(key=lambda item: (str(item["ticker"]), str(item["date"])))
    preserved_existing_output, imported_rows = _publish_yahoo_results(
        settings, output_file, csv_rows, db_rows, failures, import_db=True
    )
    return json.dumps(
        {
            "input_file": str(workbook_path),
            "output_file": str(output_file),
            "parsed_tickers": len(tickers),
            "rows_written": len(csv_rows),
            "rows_imported": imported_rows,
            "preserved_existing_output": preserved_existing_output,
            "range": {"start": start_date, "end": end_date},
            "pause_seconds": pause_seconds,
            "batch_size": batch_size,
            "batch_pause_seconds": batch_pause_seconds,
            "failure_count": len(failures),
            "sample_failures": failures[:10],
        },
        indent=2,
    )
