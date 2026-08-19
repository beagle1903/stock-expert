from __future__ import annotations

import csv
import json
import math
import re
from datetime import date
from pathlib import Path

from stock_expert.config import Settings
from stock_expert.database import persist_daily_snapshot
from stock_expert.models import MarketSnapshot
from stock_expert.trading_calendar import previous_trading_session


HEADER_MAP = str.maketrans(
    {
        "İ": "I",
        "I": "I",
        "ı": "i",
        "Ş": "S",
        "ş": "s",
        "Ğ": "G",
        "ğ": "g",
        "Ü": "U",
        "ü": "u",
        "Ö": "O",
        "ö": "o",
        "Ç": "C",
        "ç": "c",
    }
)


def _normalize_key(value: str) -> str:
    normalized = value.translate(HEADER_MAP).upper().strip()
    return "".join(ch for ch in normalized if ch.isalnum())


CORPORATE_SUFFIXES = (
    ("ANONIM", "ORTAKLIGI"),
    ("ANONIM", "SIRKETI"),
    ("ANONIM", "SIRKET"),
    ("T", "A", "S"),
    ("A", "S"),
    ("TAS",),
    ("AS",),
)
MIN_LIVE_SOURCE_ROWS = 500
MIN_LIVE_TICKER_COVERAGE = 0.75


class DailyCsvError(RuntimeError):
    """Raised when a daily CSV bundle is unsafe to persist."""


def _company_alias_keys(value: str) -> set[str]:
    exact = _normalize_key(value)
    aliases = {exact} if exact else set()
    normalized = value.translate(HEADER_MAP).upper().strip()
    tokens = re.findall(r"[A-Z0-9]+", normalized)

    for suffix in CORPORATE_SUFFIXES:
        if len(tokens) >= len(suffix) and tuple(tokens[-len(suffix) :]) == suffix:
            stripped = "".join(tokens[: -len(suffix)])
            if stripped:
                aliases.add(stripped)
            break
    return aliases


ALLOWED_NON_EQUITY_SOURCE_KEYS = {
    "HEDEFPORTFOYYONETIMIAS",
}


def _is_non_equity_key(key: str) -> bool:
    non_equity_markers = (
        "PORTFOYYONETIMI",
        "PORTFOYYON",
        "GYF",
        "FONUY",
    )
    return any(marker in key for marker in non_equity_markers)


def _parse_number(value: str, decimal_separator: str = ",") -> float:
    if decimal_separator not in {",", "."}:
        raise ValueError("decimal_separator must be ',' or '.'")

    text = value.strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return 0.0
    text = text.replace("%", "")
    multiplier = 1.0
    if text.endswith("Mlr"):
        text = text[:-3]
        multiplier = 1_000_000_000
    elif text.endswith("Mln"):
        text = text[:-3]
        multiplier = 1_000_000
    elif text.endswith("B"):
        text = text[:-1]
        multiplier = 1_000_000_000
    elif text.endswith("T"):
        text = text[:-1]
        multiplier = 1_000_000_000_000
    elif text.endswith("M"):
        text = text[:-1]
        multiplier = 1_000_000
    elif text.endswith("K"):
        text = text[:-1]
        multiplier = 1_000
    grouping_separator = "." if decimal_separator == "," else ","
    text = text.replace(grouping_separator, "").replace(decimal_separator, ".")
    return float(text) * multiplier


def _parse_optional_number(value: str, decimal_separator: str = ",") -> float:
    try:
        parsed = _parse_number(value, decimal_separator=decimal_separator)
        return parsed if math.isfinite(parsed) else 0.0
    except (AttributeError, ValueError):
        return 0.0


def _parse_required_row_number(row: dict[str, str], key: str, decimal_separator: str = ",") -> float:
    parsed = _parse_number(row[key], decimal_separator=decimal_separator)
    if not math.isfinite(parsed):
        raise ValueError(f"{key} must be finite")
    return parsed


def _detect_decimal_separator(rows: list[dict[str, str]]) -> str:
    for row in rows:
        value = row.get("FARK", "").strip().replace("%", "")
        match = re.search(r"[.,](\d{1,4})$", value)
        if match:
            return value[match.start()]
    return ","


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {_normalize_key(key): (value or "").strip() for key, value in row.items() if key}
            rows.append(normalized)
        return rows


def _load_ticker_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        candidates: dict[str, set[str]] = {}
        for row in reader:
            ticker = (row.get("ticker", "") or "").strip().upper()
            company_key = (row.get("company_key", "") or "").strip()
            if not ticker or not company_key:
                continue

            aliases = {company_key, _normalize_key(ticker)}
            for field in ("company_name", "matched_name"):
                aliases.update(_company_alias_keys((row.get(field, "") or "").strip()))
            for alias in aliases:
                if alias:
                    candidates.setdefault(alias, set()).add(ticker)

        return {alias: next(iter(tickers)) for alias, tickers in candidates.items() if len(tickers) == 1}


def _resolve_ticker(ticker_map: dict[str, str], company_name: str) -> str | None:
    matches = {ticker_map[alias] for alias in _company_alias_keys(company_name) if alias in ticker_map}
    return next(iter(matches)) if len(matches) == 1 else None


def _validate_live_ticker_coverage(source_rows: int, eligible_rows: int, distinct_tickers: int) -> float:
    coverage = distinct_tickers / eligible_rows if eligible_rows else 0.0
    if source_rows >= MIN_LIVE_SOURCE_ROWS and coverage < MIN_LIVE_TICKER_COVERAGE:
        raise DailyCsvError(
            "Daily CSV ticker coverage is too low for publication: "
            f"{distinct_tickers}/{eligible_rows} ({coverage:.1%}); "
            f"required at least {MIN_LIVE_TICKER_COVERAGE:.0%}"
        )
    return coverage


def import_daily_csv_command(settings: Settings, snapshot_date: str, data_dir: str = "data") -> str:
    target_date = date.fromisoformat(snapshot_date)
    base = settings.base_dir / data_dir
    ticker_map = _load_ticker_map(settings.data_dir / "ticker_map.csv")
    fiyat = _read_csv(base / "fiyat.csv")
    performans = _read_csv(base / "performans.csv")
    teknik = _read_csv(base / "teknik.csv")
    temel = _read_csv(base / "temel.csv")
    decimal_separator = _detect_decimal_separator(fiyat)

    performans_map = {_normalize_key(row.get("ISIM", "")): row for row in performans if row.get("ISIM")}
    teknik_map = {_normalize_key(row.get("ISIM", "")): row for row in teknik if row.get("ISIM")}
    temel_map = {_normalize_key(row.get("ISIM", "")): row for row in temel if row.get("ISIM")}

    snapshots: list[MarketSnapshot] = []
    price_rows: list[tuple[str, date, float, float, float]] = []
    mapped_count = 0
    fallback_count = 0
    skipped_non_equity_count = 0
    skipped_unmapped_count = 0
    skipped_malformed_count = 0

    for row in fiyat:
        company_name = row.get("ISIM", "").strip()
        if not company_name:
            continue
        key = _normalize_key(company_name)
        if _is_non_equity_key(key) and key not in ALLOWED_NON_EQUITY_SOURCE_KEYS:
            skipped_non_equity_count += 1
            continue
        perf = performans_map.get(key)
        tech = teknik_map.get(key)
        fund = temel_map.get(key)
        if not perf or not tech or not fund:
            continue

        ticker = _resolve_ticker(ticker_map, company_name)
        if not ticker:
            fallback_count += 1
            skipped_unmapped_count += 1
            continue
        mapped_count += 1

        try:
            last_price = _parse_required_row_number(row, "SON", decimal_separator)
            daily_pct = _parse_required_row_number(row, "FARK", decimal_separator)
            reference_price = last_price / (1 + (daily_pct / 100.0)) if daily_pct != -100 else last_price
            volume = _parse_required_row_number(row, "HAC", decimal_separator)
            high_price = _parse_required_row_number(row, "YUKSEK", decimal_separator)
            low_price = _parse_required_row_number(row, "DUSUK", decimal_separator)
            weekly_perf_pct = _parse_required_row_number(perf, "HAFTALIK", decimal_separator)
            monthly_perf_pct = _parse_required_row_number(perf, "1AYLIK", decimal_separator)
            ytd_perf_pct = _parse_required_row_number(perf, "YTD", decimal_separator)
            yearly_perf_pct = _parse_required_row_number(perf, "1YILLIK", decimal_separator)
            if last_price <= 0 or high_price <= 0 or low_price <= 0 or volume < 0:
                raise ValueError("price and volume values are outside their valid domain")
        except (KeyError, ValueError):
            skipped_malformed_count += 1
            continue

        snapshots.append(
            MarketSnapshot(
                date=target_date,
                ticker=ticker,
                company_name=company_name,
                last_price=last_price,
                high_price=high_price,
                low_price=low_price,
                daily_change_pct=daily_pct,
                volume=volume,
                weekly_perf_pct=weekly_perf_pct,
                monthly_perf_pct=monthly_perf_pct,
                ytd_perf_pct=ytd_perf_pct,
                yearly_perf_pct=yearly_perf_pct,
                technical_hourly=tech["SAATLIK"].strip(),
                technical_daily=tech["GUNLUK"].strip(),
                technical_weekly=tech["HAFTALIK"].strip(),
                technical_monthly=tech["AYLIK"].strip(),
                avg_volume_3m=_parse_optional_number(fund.get("ORTALAMAHACIM3AY", ""), decimal_separator),
                market_cap=_parse_optional_number(fund.get("PIYASADEGERI", ""), decimal_separator),
                beta=_parse_optional_number(fund.get("BETA", ""), decimal_separator),
                revenue=_parse_optional_number(fund.get("GELIR", ""), decimal_separator),
                pe_ratio=_parse_optional_number(fund.get("FIYATKAZANCORANI", ""), decimal_separator),
            )
        )
        price_rows.append((ticker, target_date, reference_price, last_price, volume))

    distinct_tickers = len({snapshot.ticker for snapshot in snapshots})
    eligible_rows = max(len(fiyat) - skipped_non_equity_count, 0)
    ticker_coverage = _validate_live_ticker_coverage(len(fiyat), eligible_rows, distinct_tickers)

    snapshot_id = persist_daily_snapshot(
        settings=settings,
        snapshot_date=target_date,
        source_label="daily_csv",
        source_dir=data_dir,
        market_rows=snapshots,
        price_rows=price_rows,
    )
    return json.dumps(
        {
            "snapshot_id": snapshot_id,
            "snapshot_date": target_date.isoformat(),
            "rows_read": len(snapshots),
            "distinct_generated_tickers": distinct_tickers,
            "mapped_count": mapped_count,
            "fallback_count": fallback_count,
            "skipped_non_equity_count": skipped_non_equity_count,
            "skipped_unmapped_count": skipped_unmapped_count,
            "skipped_malformed_count": skipped_malformed_count,
            "decimal_separator": decimal_separator,
            "ticker_coverage": round(ticker_coverage, 4),
            "price_basis": "previous_close_to_last_from_daily_change_pct",
            "source_files": ["fiyat.csv", "performans.csv", "teknik.csv", "temel.csv"],
        },
        indent=2,
    )


def import_daily_csv_folder_command(settings: Settings, folder: str) -> str:
    folder_path = settings.base_dir / folder
    folder_date = folder_path.name
    target_trade_date = None
    if len(folder_date) == 8 and folder_date.isdigit():
        label_date = date(int(folder_date[:4]), int(folder_date[4:6]), int(folder_date[6:]))
        target_trade_date = label_date
        snapshot_date = previous_trading_session(label_date).isoformat()
    else:
        snapshot_date = folder_date
    result = json.loads(import_daily_csv_command(settings=settings, snapshot_date=snapshot_date, data_dir=folder))
    if target_trade_date is not None:
        result["target_trade_date"] = target_trade_date.isoformat()
    return json.dumps(result, indent=2)
