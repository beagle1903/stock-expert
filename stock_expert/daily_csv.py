from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from stock_expert.config import Settings
from stock_expert.database import init_db, replace_imported_day, upsert_market_snapshots, upsert_prices
from stock_expert.models import MarketSnapshot


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


def _parse_number(value: str) -> float:
    text = value.strip().replace(".", "").replace(",", ".")
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
    return float(text) * multiplier


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
        return {
            (row.get("company_key", "") or "").strip(): (row.get("ticker", "") or "").strip().upper()
            for row in reader
            if (row.get("company_key", "") or "").strip() and (row.get("ticker", "") or "").strip()
        }


def import_daily_csv_command(settings: Settings, snapshot_date: str, data_dir: str = "data") -> str:
    target_date = date.fromisoformat(snapshot_date)
    base = settings.base_dir / data_dir
    ticker_map = _load_ticker_map(settings.data_dir / "ticker_map.csv")
    fiyat = _read_csv(base / "fiyat.csv")
    performans = _read_csv(base / "performans.csv")
    teknik = _read_csv(base / "teknik.csv")
    temel = _read_csv(base / "temel.csv")

    performans_map = {_normalize_key(row.get("ISIM", "")): row for row in performans if row.get("ISIM")}
    teknik_map = {_normalize_key(row.get("ISIM", "")): row for row in teknik if row.get("ISIM")}
    temel_map = {_normalize_key(row.get("ISIM", "")): row for row in temel if row.get("ISIM")}

    snapshots: list[MarketSnapshot] = []
    price_rows: list[tuple[str, date, float, float, float]] = []
    mapped_count = 0
    fallback_count = 0

    for row in fiyat:
        company_name = row.get("ISIM", "").strip()
        if not company_name:
            continue
        key = _normalize_key(company_name)
        perf = performans_map.get(key)
        tech = teknik_map.get(key)
        fund = temel_map.get(key)
        if not perf or not tech or not fund:
            continue

        ticker = ticker_map.get(key, key[:12])
        if key in ticker_map:
            mapped_count += 1
        else:
            fallback_count += 1
        last_price = _parse_number(row["SON"])
        daily_pct = _parse_number(row["FARK"])
        open_price = last_price / (1 + (daily_pct / 100.0)) if daily_pct != -100 else last_price
        volume = _parse_number(row["HAC"])

        snapshots.append(
            MarketSnapshot(
                date=target_date,
                ticker=ticker,
                company_name=company_name,
                last_price=last_price,
                high_price=_parse_number(row["YUKSEK"]),
                low_price=_parse_number(row["DUSUK"]),
                daily_change_pct=daily_pct,
                volume=volume,
                weekly_perf_pct=_parse_number(perf["HAFTALIK"]),
                monthly_perf_pct=_parse_number(perf["1AYLIK"]),
                ytd_perf_pct=_parse_number(perf["YTD"]),
                yearly_perf_pct=_parse_number(perf["1YILLIK"]),
                technical_hourly=tech["SAATLIK"].strip(),
                technical_daily=tech["GUNLUK"].strip(),
                technical_weekly=tech["HAFTALIK"].strip(),
                technical_monthly=tech["AYLIK"].strip(),
                avg_volume_3m=_parse_number(fund["ORTALAMAHACIM3AY"]),
                market_cap=_parse_number(fund["PIYASADEGERI"]),
                beta=_parse_number(fund["BETA"]),
            )
        )
        price_rows.append((ticker, target_date, open_price, last_price, volume))

    init_db(settings)
    replace_imported_day(settings, target_date)
    upsert_market_snapshots(settings, snapshots)
    upsert_prices(settings, price_rows)
    distinct_tickers = len({snapshot.ticker for snapshot in snapshots})

    return json.dumps(
        {
            "snapshot_date": target_date.isoformat(),
            "rows_read": len(snapshots),
            "distinct_generated_tickers": distinct_tickers,
            "mapped_count": mapped_count,
            "fallback_count": fallback_count,
            "source_files": ["fiyat.csv", "performans.csv", "teknik.csv", "temel.csv"],
        },
        indent=2,
    )


def import_daily_csv_folder_command(settings: Settings, folder: str) -> str:
    folder_path = settings.base_dir / folder
    snapshot_date = folder_path.name
    if len(snapshot_date) == 8 and snapshot_date.isdigit():
        snapshot_date = f"{snapshot_date[:4]}-{snapshot_date[4:6]}-{snapshot_date[6:]}"
    return import_daily_csv_command(settings=settings, snapshot_date=snapshot_date, data_dir=folder)
