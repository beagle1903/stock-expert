from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterable, Iterator

from stock_expert.config import Settings
from stock_expert.constants import MIN_DAILY_WIN_RETURN
from stock_expert.models import MarketSnapshot, PickRow, PriceBar, SignalRow, Weights


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_label TEXT NOT NULL,
    source_dir TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stocks (
    snapshot_id INTEGER NOT NULL DEFAULT 0,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (snapshot_id, ticker)
);

CREATE TABLE IF NOT EXISTS signals (
    snapshot_id INTEGER NOT NULL DEFAULT 0,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    kap_score REAL NOT NULL,
    momentum REAL NOT NULL,
    volume_spike REAL NOT NULL,
    PRIMARY KEY (snapshot_id, ticker)
);

CREATE TABLE IF NOT EXISTS picks (
    snapshot_id INTEGER NOT NULL DEFAULT 0,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    score REAL NOT NULL,
    kap REAL NOT NULL,
    momentum REAL NOT NULL,
    volume REAL NOT NULL,
    risk TEXT NOT NULL,
    horizon TEXT NOT NULL,
    selection_bucket TEXT NOT NULL DEFAULT 'score_ranked',
    PRIMARY KEY (snapshot_id, ticker)
);

CREATE TABLE IF NOT EXISTS weights (
    date TEXT PRIMARY KEY,
    kap_weight REAL NOT NULL,
    momentum_weight REAL NOT NULL,
    volume_weight REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    snapshot_id INTEGER NOT NULL DEFAULT 0,
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
    revenue REAL NOT NULL DEFAULT 0,
    pe_ratio REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_id, ticker)
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
    volume_weight REAL NOT NULL,
    signal_snapshot_id INTEGER,
    weight_date TEXT,
    strategy_version TEXT NOT NULL DEFAULT 'score-v1',
    UNIQUE (as_of_date, review_date)
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

CREATE TABLE IF NOT EXISTS candidate_outcomes (
    review_run_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    review_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    candidate_rank INTEGER NOT NULL,
    score REAL NOT NULL,
    momentum REAL NOT NULL,
    volume REAL NOT NULL,
    technical REAL NOT NULL,
    fundamental REAL NOT NULL,
    quality REAL NOT NULL,
    setup_penalty REAL NOT NULL,
    selected_score_ranked INTEGER NOT NULL,
    selected_bucketed INTEGER NOT NULL,
    bucketed_bucket TEXT,
    return_pct REAL NOT NULL,
    won INTEGER NOT NULL,
    PRIMARY KEY (signal_date, review_date, ticker),
    FOREIGN KEY (review_run_id) REFERENCES review_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_runs_date_id
ON snapshot_runs(snapshot_date, id DESC);

CREATE INDEX IF NOT EXISTS idx_candidate_outcomes_review_rank
ON candidate_outcomes(review_date DESC, candidate_rank);
"""


@contextmanager
def connect(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(settings: Settings) -> None:
    with connect(settings) as conn:
        conn.executescript(SCHEMA)
        _migrate_intraday_snapshots(conn)
        _ensure_market_snapshot_enrichment_columns(conn)
        _ensure_picks_selection_bucket_column(conn)
        _ensure_review_integrity(conn)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _legacy_snapshot_dates(conn: sqlite3.Connection) -> list[str]:
    dates: set[str] = set()
    for table in ("stocks", "signals", "picks", "market_snapshots"):
        if conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
            dates.update(row["date"] for row in conn.execute(f"SELECT DISTINCT date FROM {table}"))
    return sorted(dates)


def _legacy_snapshot_map_sql() -> str:
    return """
        SELECT snapshot_date, MIN(id) AS id
        FROM snapshot_runs
        WHERE source_label = 'legacy'
        GROUP BY snapshot_date
    """


def _migrate_intraday_snapshots(conn: sqlite3.Connection) -> None:
    old_schema = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'stocks'").fetchone()
    if not old_schema or _has_column(conn, "stocks", "snapshot_id"):
        return

    for day in _legacy_snapshot_dates(conn):
        conn.execute(
            """
            INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
            VALUES (?, 'legacy', 'data archive')
            """,
            (day,),
        )

    legacy_tables = [table for table in ("stocks", "signals", "picks", "market_snapshots") if not _has_column(conn, table, "snapshot_id")]
    for table in legacy_tables:
        conn.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")

    conn.executescript(SCHEMA)
    snapshot_map = _legacy_snapshot_map_sql()
    if "stocks" in legacy_tables:
        conn.execute(
            f"""
            INSERT INTO stocks (snapshot_id, ticker, date, open_price, close_price, volume)
            SELECT m.id, s.ticker, s.date, s.open_price, s.close_price, s.volume
            FROM stocks_legacy s
            JOIN ({snapshot_map}) m ON m.snapshot_date = s.date
            """
        )
        conn.execute("DROP TABLE stocks_legacy")
    if "signals" in legacy_tables:
        conn.execute(
            f"""
            INSERT INTO signals (snapshot_id, ticker, date, kap_score, momentum, volume_spike)
            SELECT m.id, s.ticker, s.date, s.kap_score, s.momentum, s.volume_spike
            FROM signals_legacy s
            JOIN ({snapshot_map}) m ON m.snapshot_date = s.date
            """
        )
        conn.execute("DROP TABLE signals_legacy")
    if "picks" in legacy_tables:
        conn.execute(
            f"""
            INSERT INTO picks (snapshot_id, date, ticker, score, kap, momentum, volume, risk, horizon)
            SELECT m.id, p.date, p.ticker, p.score, p.kap, p.momentum, p.volume, p.risk, p.horizon
            FROM picks_legacy p
            JOIN ({snapshot_map}) m ON m.snapshot_date = p.date
            """
        )
        conn.execute("DROP TABLE picks_legacy")
    if "market_snapshots" in legacy_tables:
        conn.execute(
            f"""
            INSERT INTO market_snapshots (
                snapshot_id, date, ticker, company_name, last_price, high_price, low_price,
                daily_change_pct, volume, weekly_perf_pct, monthly_perf_pct, ytd_perf_pct,
                yearly_perf_pct, technical_hourly, technical_daily, technical_weekly,
                technical_monthly, avg_volume_3m, market_cap, beta, revenue, pe_ratio
            )
            SELECT
                m.id, ms.date, ms.ticker, ms.company_name, ms.last_price, ms.high_price,
                ms.low_price, ms.daily_change_pct, ms.volume, ms.weekly_perf_pct,
                ms.monthly_perf_pct, ms.ytd_perf_pct, ms.yearly_perf_pct,
                ms.technical_hourly, ms.technical_daily, ms.technical_weekly,
                ms.technical_monthly, ms.avg_volume_3m, ms.market_cap, ms.beta, 0.0, 0.0
            FROM market_snapshots_legacy ms
            JOIN ({snapshot_map}) m ON m.snapshot_date = ms.date
            """
        )
        conn.execute("DROP TABLE market_snapshots_legacy")


def _ensure_market_snapshot_enrichment_columns(conn: sqlite3.Connection) -> None:
    if not conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'market_snapshots'").fetchone():
        return
    if not _has_column(conn, "market_snapshots", "revenue"):
        conn.execute("ALTER TABLE market_snapshots ADD COLUMN revenue REAL NOT NULL DEFAULT 0")
    if not _has_column(conn, "market_snapshots", "pe_ratio"):
        conn.execute("ALTER TABLE market_snapshots ADD COLUMN pe_ratio REAL NOT NULL DEFAULT 0")


def _ensure_picks_selection_bucket_column(conn: sqlite3.Connection) -> None:
    if not conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'picks'").fetchone():
        return
    if not _has_column(conn, "picks", "selection_bucket"):
        conn.execute("ALTER TABLE picks ADD COLUMN selection_bucket TEXT NOT NULL DEFAULT 'score_ranked'")


def _ensure_review_integrity(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "review_runs", "signal_snapshot_id"):
        conn.execute("ALTER TABLE review_runs ADD COLUMN signal_snapshot_id INTEGER")
    if not _has_column(conn, "review_runs", "weight_date"):
        conn.execute("ALTER TABLE review_runs ADD COLUMN weight_date TEXT")
    if not _has_column(conn, "review_runs", "strategy_version"):
        conn.execute("ALTER TABLE review_runs ADD COLUMN strategy_version TEXT NOT NULL DEFAULT 'score-v1'")
    if not _has_column(conn, "candidate_outcomes", "review_run_id"):
        conn.execute("ALTER TABLE candidate_outcomes ADD COLUMN review_run_id INTEGER")

    duplicate_ids = [
        int(row["id"])
        for row in conn.execute(
            """
            SELECT id
            FROM review_runs
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM review_runs
                GROUP BY as_of_date, review_date
            )
            """
        )
    ]
    if duplicate_ids:
        placeholders = ",".join("?" for _ in duplicate_ids)
        conn.execute(f"DELETE FROM review_pick_results WHERE review_run_id IN ({placeholders})", duplicate_ids)
        conn.execute(f"DELETE FROM review_runs WHERE id IN ({placeholders})", duplicate_ids)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_review_runs_signal_review
        ON review_runs(as_of_date, review_date)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_outcomes_review_rank
        ON candidate_outcomes(review_date DESC, candidate_rank)
        """
    )


def create_snapshot_run(settings: Settings, snapshot_date: date, source_label: str, source_dir: str) -> int:
    init_db(settings)
    with connect(settings) as conn:
        cursor = conn.execute(
            """
            INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
            VALUES (?, ?, ?)
            """,
            (snapshot_date.isoformat(), source_label, source_dir),
        )
        return int(cursor.lastrowid)


def persist_daily_snapshot(
    settings: Settings,
    snapshot_date: date,
    source_label: str,
    source_dir: str,
    market_rows: Iterable[MarketSnapshot],
    price_rows: Iterable[tuple[str, date, float, float, float]],
) -> int:
    init_db(settings)
    with connect(settings) as conn:
        cursor = conn.execute(
            """
            INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
            VALUES (?, ?, ?)
            """,
            (snapshot_date.isoformat(), source_label, source_dir),
        )
        snapshot_id = int(cursor.lastrowid)
        _upsert_market_snapshots_conn(conn, market_rows, snapshot_id)
        _upsert_prices_conn(
            conn,
            [(snapshot_id, ticker, day.isoformat(), open_p, close_p, volume) for ticker, day, open_p, close_p, volume in price_rows],
        )
        return snapshot_id


def get_latest_snapshot_id(settings: Settings, target_date: date) -> int | None:
    init_db(settings)
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT id
            FROM snapshot_runs
            WHERE snapshot_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (target_date.isoformat(),),
        ).fetchone()
    return int(row["id"]) if row else None


def _latest_snapshot_ids_between(conn: sqlite3.Connection, start_date: date, end_date: date) -> list[int]:
    rows = conn.execute(
        """
        SELECT id, snapshot_date
        FROM snapshot_runs
        WHERE snapshot_date BETWEEN ? AND ?
        ORDER BY snapshot_date DESC, id DESC
        """,
        (start_date.isoformat(), end_date.isoformat()),
    )
    seen: set[str] = set()
    snapshot_ids: list[int] = []
    for row in rows:
        if row["snapshot_date"] in seen:
            continue
        seen.add(row["snapshot_date"])
        snapshot_ids.append(int(row["id"]))
    return snapshot_ids


def upsert_prices(settings: Settings, rows: Iterable[tuple]) -> None:
    raw_rows = list(rows)
    init_db(settings)
    with connect(settings) as conn:
        legacy_dates = sorted({row[1] for row in raw_rows if len(row) == 5})
        snapshot_ids: dict[date, int] = {}
        if legacy_dates:
            placeholders = ",".join("?" for _ in legacy_dates)
            for row in conn.execute(
                f"""
                SELECT id, snapshot_date
                FROM snapshot_runs
                WHERE snapshot_date IN ({placeholders})
                ORDER BY id DESC
                """,
                [day.isoformat() for day in legacy_dates],
            ):
                snapshot_ids.setdefault(date.fromisoformat(row["snapshot_date"]), int(row["id"]))
            for day in legacy_dates:
                if day in snapshot_ids:
                    continue
                cursor = conn.execute(
                    """
                    INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
                    VALUES (?, 'legacy', 'unknown')
                    """,
                    (day.isoformat(),),
                )
                snapshot_ids[day] = int(cursor.lastrowid)

        normalized = []
        for row in raw_rows:
            if len(row) == 6:
                snapshot_id, ticker, day, open_p, close_p, volume = row
            else:
                ticker, day, open_p, close_p, volume = row
                snapshot_id = snapshot_ids[day]
            normalized.append((snapshot_id, ticker, day.isoformat(), open_p, close_p, volume))
        _upsert_prices_conn(conn, normalized)


def _upsert_prices_conn(conn: sqlite3.Connection, rows: Iterable[tuple]) -> None:
    conn.executemany(
        """
        INSERT INTO stocks (snapshot_id, ticker, date, open_price, close_price, volume)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
            open_price = excluded.open_price,
            close_price = excluded.close_price,
            volume = excluded.volume
        """,
        rows,
    )


def upsert_signals(settings: Settings, rows: Iterable[SignalRow], snapshot_id: int) -> None:
    with connect(settings) as conn:
        conn.executemany(
            """
            INSERT INTO signals (snapshot_id, ticker, date, kap_score, momentum, volume_spike)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
                kap_score = excluded.kap_score,
                momentum = excluded.momentum,
                volume_spike = excluded.volume_spike
            """,
            [(snapshot_id, row.ticker, row.date.isoformat(), 0.0, row.momentum, row.volume_spike) for row in rows],
        )


def replace_picks_for_date(settings: Settings, rows: Iterable[PickRow], target_date: date, snapshot_id: int | None = None) -> None:
    snapshot_id = snapshot_id or get_latest_snapshot_id(settings, target_date) or create_snapshot_run(settings, target_date, "legacy", "unknown")
    with connect(settings) as conn:
        conn.execute("DELETE FROM picks WHERE snapshot_id = ?", (snapshot_id,))
        conn.executemany(
            """
            INSERT INTO picks (snapshot_id, date, ticker, score, kap, momentum, volume, risk, horizon, selection_bucket)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_id,
                    row.date.isoformat(),
                    row.ticker,
                    row.score,
                    0.0,
                    row.momentum,
                    row.volume,
                    row.risk,
                    row.horizon,
                    row.selection_bucket,
                )
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


def upsert_market_snapshots(settings: Settings, rows: Iterable[MarketSnapshot], snapshot_id: int) -> None:
    with connect(settings) as conn:
        _upsert_market_snapshots_conn(conn, rows, snapshot_id)


def _upsert_market_snapshots_conn(
    conn: sqlite3.Connection,
    rows: Iterable[MarketSnapshot],
    snapshot_id: int,
) -> None:
    conn.executemany(
            """
            INSERT INTO market_snapshots (
                snapshot_id, date, ticker, company_name, last_price, high_price, low_price, daily_change_pct, volume,
                weekly_perf_pct, monthly_perf_pct, ytd_perf_pct, yearly_perf_pct,
                technical_hourly, technical_daily, technical_weekly, technical_monthly,
                avg_volume_3m, market_cap, beta, revenue, pe_ratio
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
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
                beta = excluded.beta,
                revenue = excluded.revenue,
                pe_ratio = excluded.pe_ratio
            """,
            [
                (
                    snapshot_id,
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
                    row.revenue,
                    row.pe_ratio,
                )
                for row in rows
            ],
    )


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


def get_weights_as_of(settings: Settings, target_date: date) -> Weights | None:
    init_db(settings)
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT date, momentum_weight, volume_weight
            FROM weights
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (target_date.isoformat(),),
        ).fetchone()
    if row is None:
        return None
    return Weights(
        date=date.fromisoformat(row["date"]),
        momentum_weight=row["momentum_weight"],
        volume_weight=row["volume_weight"],
    )


def get_pick_results(settings: Settings, signal_date: date, target_date: date) -> list[sqlite3.Row]:
    signal_snapshot_id = get_latest_snapshot_id(settings, signal_date)
    target_snapshot_id = get_latest_snapshot_id(settings, target_date)
    if signal_snapshot_id is None or target_snapshot_id is None:
        return []
    with connect(settings) as conn:
        return list(
            conn.execute(
                """
                SELECT
                    p.date AS signal_date,
                    ? AS target_date,
                    p.ticker,
                    p.score,
                    p.selection_bucket,
                    s.open_price,
                    s.close_price
                FROM picks p
                JOIN stocks s
                  ON s.ticker = p.ticker
                 AND s.snapshot_id = ?
                WHERE p.snapshot_id = ?
                ORDER BY p.score DESC
                """,
                (target_date.isoformat(), target_snapshot_id, signal_snapshot_id),
            )
        )


def get_candidate_outcomes(settings: Settings, limit_sessions: int = 20) -> list[sqlite3.Row]:
    init_db(settings)
    with connect(settings) as conn:
        return list(
            conn.execute(
                """
                SELECT *
                FROM candidate_outcomes
                WHERE review_date IN (
                    SELECT DISTINCT review_date
                    FROM candidate_outcomes
                    ORDER BY review_date DESC
                    LIMIT ?
                )
                ORDER BY review_date DESC, candidate_rank ASC
                """,
                (limit_sessions,),
            )
        )


def get_review_run(settings: Settings, as_of: date, review_date: date) -> sqlite3.Row | None:
    init_db(settings)
    with connect(settings) as conn:
        return conn.execute(
            """
            SELECT id, momentum_weight, volume_weight
            FROM review_runs
            WHERE as_of_date = ? AND review_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (as_of.isoformat(), review_date.isoformat()),
        ).fetchone()


def get_recent_review_runs(
    settings: Settings,
    limit: int = 20,
    before_review_date: date | None = None,
) -> list[sqlite3.Row]:
    init_db(settings)
    with connect(settings) as conn:
        where = "WHERE pick_count > 0"
        params: list[object] = []
        if before_review_date is not None:
            where += " AND review_date < ?"
            params.append(before_review_date.isoformat())
        params.append(limit)
        return list(
            conn.execute(
                f"""
                SELECT as_of_date, review_date, avg_return, win_rate, pick_count, wins
                FROM review_runs
                {where}
                ORDER BY review_date DESC
                LIMIT ?
                """,
                params,
            )
        )


def persist_review_bundle(
    settings: Settings,
    as_of: date,
    review_date: date,
    avg_return: float,
    win_rate: float,
    picks: Iterable[sqlite3.Row],
    weights: Weights,
    candidate_outcomes: Iterable[dict[str, object]],
    signal_snapshot_id: int | None,
    strategy_version: str = "score-v1",
) -> tuple[int, bool]:
    init_db(settings)
    pick_rows = list(picks)
    outcome_rows = list(candidate_outcomes)
    wins = sum(1 for row in pick_rows if _review_pick_won(row))
    with connect(settings) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO review_runs (
                as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                momentum_weight, volume_weight, signal_snapshot_id, weight_date,
                strategy_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                signal_snapshot_id,
                weights.date.isoformat(),
                strategy_version,
            ),
        )
        if cursor.rowcount == 0:
            existing = conn.execute(
                """
                SELECT id
                FROM review_runs
                WHERE as_of_date = ? AND review_date = ?
                """,
                (as_of.isoformat(), review_date.isoformat()),
            ).fetchone()
            return int(existing["id"]), False

        review_run_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO weights (date, kap_weight, momentum_weight, volume_weight)
            VALUES (?, 0.0, ?, ?)
            ON CONFLICT (date) DO UPDATE SET
                momentum_weight = excluded.momentum_weight,
                volume_weight = excluded.volume_weight
            """,
            (weights.date.isoformat(), weights.momentum_weight, weights.volume_weight),
        )
        _insert_review_pick_results_conn(conn, review_run_id, pick_rows)
        _insert_candidate_outcomes_conn(conn, review_run_id, as_of, review_date, outcome_rows)
        return review_run_id, True


def _insert_review_pick_results_conn(
    conn: sqlite3.Connection,
    review_run_id: int,
    pick_rows: Iterable[sqlite3.Row],
) -> None:
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
                1 if _review_pick_won(row) else 0,
            )
            for row in pick_rows
        ],
    )


def _insert_candidate_outcomes_conn(
    conn: sqlite3.Connection,
    review_run_id: int,
    signal_date: date,
    review_date: date,
    outcome_rows: Iterable[dict[str, object]],
) -> None:
    conn.executemany(
        """
        INSERT INTO candidate_outcomes (
            review_run_id, signal_date, review_date, ticker, candidate_rank, score,
            momentum, volume, technical, fundamental, quality, setup_penalty,
            selected_score_ranked, selected_bucketed, bucketed_bucket, return_pct, won
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                review_run_id,
                signal_date.isoformat(),
                review_date.isoformat(),
                row["ticker"],
                row["candidate_rank"],
                row["score"],
                row["momentum"],
                row["volume"],
                row["technical"],
                row["fundamental"],
                row["quality"],
                row["setup_penalty"],
                row["selected_score_ranked"],
                row["selected_bucketed"],
                row["bucketed_bucket"],
                row["return_pct"],
                row["won"],
            )
            for row in outcome_rows
        ],
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
    wins = sum(1 for row in pick_rows if _review_pick_won(row))
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
                    1 if _review_pick_won(row) else 0,
                )
                for row in pick_rows
            ],
        )
        return review_run_id


def _review_pick_won(row: sqlite3.Row) -> bool:
    if not row["open_price"]:
        return False
    return ((row["close_price"] - row["open_price"]) / row["open_price"]) >= MIN_DAILY_WIN_RETURN


def get_top_movers(settings: Settings, as_of: date, days: int, limit: int = 10) -> list[sqlite3.Row]:
    start_date = (as_of - timedelta(days=days - 1)).isoformat()
    end_date = as_of.isoformat()
    with connect(settings) as conn:
        snapshot_ids = _latest_snapshot_ids_between(conn, date.fromisoformat(start_date), date.fromisoformat(end_date))
        if not snapshot_ids:
            return []
        placeholders = ",".join("?" for _ in snapshot_ids)
        return list(
            conn.execute(
                f"""
                SELECT ticker, date, open_price, close_price, volume,
                       ((close_price - open_price) / open_price) AS day_return
                FROM stocks
                WHERE snapshot_id IN ({placeholders})
                ORDER BY day_return DESC
                LIMIT ?
                """,
                (*snapshot_ids, limit),
            )
        )


def get_prices_for_date(settings: Settings, target_date: date) -> list[PriceBar]:
    snapshot_id = get_latest_snapshot_id(settings, target_date)
    if snapshot_id is None:
        return []
    with connect(settings) as conn:
        rows = list(
            conn.execute(
                """
                SELECT ticker, date, open_price, close_price, volume
                FROM stocks
                WHERE snapshot_id = ?
                ORDER BY ticker
                """,
                (snapshot_id,),
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
        snapshot_ids = _latest_snapshot_ids_between(conn, start_date, end_date)
        if not snapshot_ids:
            return []
        placeholders = ",".join("?" for _ in snapshot_ids)
        rows = list(
            conn.execute(
                f"""
                SELECT ticker, date, open_price, close_price, volume
                FROM stocks
                WHERE snapshot_id IN ({placeholders})
                ORDER BY ticker, date
                """,
                snapshot_ids,
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
                SELECT DISTINCT snapshot_date AS date
                FROM snapshot_runs
                WHERE snapshot_date <= ?
                ORDER BY snapshot_date DESC
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
    snapshot_id = get_latest_snapshot_id(settings, target_date)
    if snapshot_id is None:
        return []
    with connect(settings) as conn:
        rows = list(
            conn.execute(
                """
                SELECT *
                FROM market_snapshots
                WHERE snapshot_id = ?
                ORDER BY company_name
                """,
                (snapshot_id,),
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
            revenue=row["revenue"],
            pe_ratio=row["pe_ratio"],
        )
        for row in rows
    ]
