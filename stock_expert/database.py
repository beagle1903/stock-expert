from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterable, Iterator

from stock_expert.config import Settings
from stock_expert.models import MarketSnapshot, PickRow, PriceBar, SignalRow, Weights


SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS signals (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    kap_score REAL NOT NULL,
    momentum REAL NOT NULL,
    volume_spike REAL NOT NULL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS picks (
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    score REAL NOT NULL,
    kap REAL NOT NULL,
    momentum REAL NOT NULL,
    volume REAL NOT NULL,
    risk TEXT NOT NULL,
    horizon TEXT NOT NULL,
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS weights (
    date TEXT PRIMARY KEY,
    kap_weight REAL NOT NULL,
    momentum_weight REAL NOT NULL,
    volume_weight REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    company_name TEXT NOT NULL,
    last_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    daily_change_pct REAL NOT NULL,
    volume REAL NOT NULL,
    weekly_perf_pct REAL NOT NULL,
    monthly_perf_pct REAL NOT NULL,
    ytd_perf_pct REAL NOT NULL,
    yearly_perf_pct REAL NOT NULL,
    technical_hourly TEXT NOT NULL,
    technical_daily TEXT NOT NULL,
    technical_weekly TEXT NOT NULL,
    technical_monthly TEXT NOT NULL,
    avg_volume_3m REAL NOT NULL,
    market_cap REAL NOT NULL,
    beta REAL NOT NULL,
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS review_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    as_of_date TEXT NOT NULL,
    review_date TEXT NOT NULL,
    avg_return REAL NOT NULL,
    win_rate REAL NOT NULL,
    pick_count INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    momentum_weight REAL NOT NULL,
    volume_weight REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS review_pick_results (
    review_run_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    score REAL NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    return_pct REAL NOT NULL,
    won INTEGER NOT NULL,
    PRIMARY KEY (review_run_id, ticker),
    FOREIGN KEY (review_run_id) REFERENCES review_runs(id)
);
"""


@contextmanager
def connect(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(settings: Settings) -> None:
    with connect(settings) as conn:
        conn.executescript(SCHEMA)


def upsert_prices(settings: Settings, rows: Iterable[tuple[str, date, float, float, float]]) -> None:
    with connect(settings) as conn:
        conn.executemany(
            """
            INSERT INTO stocks (ticker, date, open_price, close_price, volume)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date) DO UPDATE SET
                open_price = excluded.open_price,
                close_price = excluded.close_price,
                volume = excluded.volume
            """,
            [(ticker, day.isoformat(), open_p, close_p, volume) for ticker, day, open_p, close_p, volume in rows],
        )


def upsert_signals(settings: Settings, rows: Iterable[SignalRow]) -> None:
    with connect(settings) as conn:
        conn.executemany(
            """
            INSERT INTO signals (ticker, date, kap_score, momentum, volume_spike)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date) DO UPDATE SET
                kap_score = excluded.kap_score,
                momentum = excluded.momentum,
                volume_spike = excluded.volume_spike
            """,
            [(row.ticker, row.date.isoformat(), 0.0, row.momentum, row.volume_spike) for row in rows],
        )


def replace_picks_for_date(settings: Settings, rows: Iterable[PickRow], target_date: date) -> None:
    with connect(settings) as conn:
        conn.execute("DELETE FROM picks WHERE date = ?", (target_date.isoformat(),))
        conn.executemany(
            """
            INSERT INTO picks (date, ticker, score, kap, momentum, volume, risk, horizon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (row.date.isoformat(), row.ticker, row.score, 0.0, row.momentum, row.volume, row.risk, row.horizon)
                for row in rows
            ],
        )


def insert_weights(settings: Settings, row: Weights) -> None:
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO weights (date, kap_weight, momentum_weight, volume_weight)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (date) DO UPDATE SET
                kap_weight = excluded.kap_weight,
                momentum_weight = excluded.momentum_weight,
                volume_weight = excluded.volume_weight
            """,
            (row.date.isoformat(), 0.0, row.momentum_weight, row.volume_weight),
        )


def upsert_market_snapshots(settings: Settings, rows: Iterable[MarketSnapshot]) -> None:
    with connect(settings) as conn:
        conn.executemany(
            """
            INSERT INTO market_snapshots (
                date, ticker, company_name, last_price, high_price, low_price, daily_change_pct, volume,
                weekly_perf_pct, monthly_perf_pct, ytd_perf_pct, yearly_perf_pct,
                technical_hourly, technical_daily, technical_weekly, technical_monthly,
                avg_volume_3m, market_cap, beta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, ticker) DO UPDATE SET
                company_name = excluded.company_name,
                last_price = excluded.last_price,
                high_price = excluded.high_price,
                low_price = excluded.low_price,
                daily_change_pct = excluded.daily_change_pct,
                volume = excluded.volume,
                weekly_perf_pct = excluded.weekly_perf_pct,
                monthly_perf_pct = excluded.monthly_perf_pct,
                ytd_perf_pct = excluded.ytd_perf_pct,
                yearly_perf_pct = excluded.yearly_perf_pct,
                technical_hourly = excluded.technical_hourly,
                technical_daily = excluded.technical_daily,
                technical_weekly = excluded.technical_weekly,
                technical_monthly = excluded.technical_monthly,
                avg_volume_3m = excluded.avg_volume_3m,
                market_cap = excluded.market_cap,
                beta = excluded.beta
            """,
            [
                (
                    row.date.isoformat(),
                    row.ticker,
                    row.company_name,
                    row.last_price,
                    row.high_price,
                    row.low_price,
                    row.daily_change_pct,
                    row.volume,
                    row.weekly_perf_pct,
                    row.monthly_perf_pct,
                    row.ytd_perf_pct,
                    row.yearly_perf_pct,
                    row.technical_hourly,
                    row.technical_daily,
                    row.technical_weekly,
                    row.technical_monthly,
                    row.avg_volume_3m,
                    row.market_cap,
                    row.beta,
                )
                for row in rows
            ],
        )


def replace_imported_day(settings: Settings, target_date: date) -> None:
    day = target_date.isoformat()
    with connect(settings) as conn:
        conn.execute("DELETE FROM stocks WHERE date = ?", (day,))
        conn.execute("DELETE FROM market_snapshots WHERE date = ?", (day,))
        conn.execute("DELETE FROM signals WHERE date = ?", (day,))
        conn.execute("DELETE FROM picks WHERE date = ?", (day,))


def get_latest_weights(settings: Settings) -> Weights | None:
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT date, kap_weight, momentum_weight, volume_weight
            FROM weights
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return Weights(
        date=date.fromisoformat(row["date"]),
        momentum_weight=row["momentum_weight"],
        volume_weight=row["volume_weight"],
    )


def get_pick_results(settings: Settings, signal_date: date, target_date: date) -> list[sqlite3.Row]:
    with connect(settings) as conn:
        return list(
            conn.execute(
                """
                SELECT
                    p.date AS signal_date,
                    ? AS target_date,
                    p.ticker,
                    p.score,
                    s.open_price,
                    s.close_price
                FROM picks p
                JOIN stocks s
                  ON s.ticker = p.ticker
                 AND s.date = ?
                WHERE p.date = ?
                ORDER BY p.score DESC
                """,
                (target_date.isoformat(), target_date.isoformat(), signal_date.isoformat()),
            )
        )


def get_recent_picks(settings: Settings, as_of: date, days: int) -> list[sqlite3.Row]:
    start_date = (as_of - timedelta(days=days - 1)).isoformat()
    end_date = as_of.isoformat()
    with connect(settings) as conn:
        return list(
            conn.execute(
                """
                SELECT p.date, p.ticker, p.score, s.open_price, s.close_price
                FROM picks p
                JOIN stocks s
                  ON s.ticker = p.ticker
                 AND s.date = p.date
                WHERE p.date BETWEEN ? AND ?
                ORDER BY p.date DESC, p.score DESC
                """,
                (start_date, end_date),
            )
        )


def insert_review_run(
    settings: Settings,
    as_of: date,
    review_date: date,
    avg_return: float,
    win_rate: float,
    picks: Iterable[sqlite3.Row],
    weights: Weights,
) -> int:
    pick_rows = list(picks)
    wins = sum(1 for row in pick_rows if row["open_price"] and row["close_price"] > row["open_price"])
    with connect(settings) as conn:
        cursor = conn.execute(
            """
            INSERT INTO review_runs (
                as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                momentum_weight, volume_weight
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                as_of.isoformat(),
                review_date.isoformat(),
                avg_return,
                win_rate,
                len(pick_rows),
                wins,
                weights.momentum_weight,
                weights.volume_weight,
            ),
        )
        review_run_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO review_pick_results (
                review_run_id, ticker, score, open_price, close_price, return_pct, won
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    review_run_id,
                    row["ticker"],
                    row["score"],
                    row["open_price"],
                    row["close_price"],
                    (row["close_price"] - row["open_price"]) / row["open_price"] if row["open_price"] else 0.0,
                    1 if row["open_price"] and row["close_price"] > row["open_price"] else 0,
                )
                for row in pick_rows
            ],
        )
        return review_run_id


def get_top_movers(settings: Settings, as_of: date, days: int, limit: int = 10) -> list[sqlite3.Row]:
    start_date = (as_of - timedelta(days=days - 1)).isoformat()
    end_date = as_of.isoformat()
    with connect(settings) as conn:
        return list(
            conn.execute(
                """
                SELECT ticker, date, open_price, close_price, volume,
                       ((close_price - open_price) / open_price) AS day_return
                FROM stocks
                WHERE date BETWEEN ? AND ?
                ORDER BY day_return DESC
                LIMIT ?
                """,
                (start_date, end_date, limit),
            )
        )


def get_prices_for_date(settings: Settings, target_date: date) -> list[PriceBar]:
    with connect(settings) as conn:
        rows = list(
            conn.execute(
                """
                SELECT ticker, date, open_price, close_price, volume
                FROM stocks
                WHERE date = ?
                ORDER BY ticker
                """,
                (target_date.isoformat(),),
            )
        )
    return [
        PriceBar(
            ticker=row["ticker"],
            date=date.fromisoformat(row["date"]),
            open_price=row["open_price"],
            close_price=row["close_price"],
            volume=row["volume"],
        )
        for row in rows
    ]


def get_prices_between(settings: Settings, start_date: date, end_date: date) -> list[PriceBar]:
    with connect(settings) as conn:
        rows = list(
            conn.execute(
                """
                SELECT ticker, date, open_price, close_price, volume
                FROM stocks
                WHERE date BETWEEN ? AND ?
                ORDER BY ticker, date
                """,
                (start_date.isoformat(), end_date.isoformat()),
            )
        )
    return [
        PriceBar(
            ticker=row["ticker"],
            date=date.fromisoformat(row["date"]),
            open_price=row["open_price"],
            close_price=row["close_price"],
            volume=row["volume"],
        )
        for row in rows
    ]


def get_recent_price_history(settings: Settings, as_of: date, bars: int) -> list[PriceBar]:
    with connect(settings) as conn:
        date_rows = list(
            conn.execute(
                """
                SELECT DISTINCT date
                FROM stocks
                WHERE date <= ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (as_of.isoformat(), bars),
            )
        )
    if not date_rows:
        return []
    if date_rows[0]["date"] != as_of.isoformat():
        return []
    start_date = date.fromisoformat(date_rows[-1]["date"])
    return get_prices_between(settings, start_date, as_of)


def get_market_snapshots_for_date(settings: Settings, target_date: date) -> list[MarketSnapshot]:
    with connect(settings) as conn:
        rows = list(
            conn.execute(
                """
                SELECT *
                FROM market_snapshots
                WHERE date = ?
                ORDER BY company_name
                """,
                (target_date.isoformat(),),
            )
        )
    return [
        MarketSnapshot(
            date=date.fromisoformat(row["date"]),
            ticker=row["ticker"],
            company_name=row["company_name"],
            last_price=row["last_price"],
            high_price=row["high_price"],
            low_price=row["low_price"],
            daily_change_pct=row["daily_change_pct"],
            volume=row["volume"],
            weekly_perf_pct=row["weekly_perf_pct"],
            monthly_perf_pct=row["monthly_perf_pct"],
            ytd_perf_pct=row["ytd_perf_pct"],
            yearly_perf_pct=row["yearly_perf_pct"],
            technical_hourly=row["technical_hourly"],
            technical_daily=row["technical_daily"],
            technical_weekly=row["technical_weekly"],
            technical_monthly=row["technical_monthly"],
            avg_volume_3m=row["avg_volume_3m"],
            market_cap=row["market_cap"],
            beta=row["beta"],
        )
        for row in rows
    ]
