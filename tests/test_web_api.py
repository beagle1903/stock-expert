from __future__ import annotations

import os
import json
import subprocess
import tempfile
import threading
import unittest
from datetime import date, datetime
from pathlib import Path
from urllib.request import urlopen

from stock_expert.config import Settings
from stock_expert.database import connect, init_db
from stock_expert.web_api import (
    DEFAULT_PORT,
    REQUIRED_CSV_FILES,
    RoutineApiServer,
    RoutineRequestError,
    build_routine_preview,
    execute_routine,
    load_review_by_id,
    load_review_history,
    load_latest_picks,
    load_latest_review,
    load_strategy_playback,
    load_strategy_evidence,
)


class RoutineWebApiTests(unittest.TestCase):
    def test_default_api_port_avoids_the_windows_reserved_development_range(self) -> None:
        self.assertEqual(DEFAULT_PORT, 18765)
        self.assertFalse(8760 <= DEFAULT_PORT <= 8859)

    def setUp(self) -> None:
        workspace_tmp = Path(".test_tmp")
        workspace_tmp.mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=workspace_tmp)
        self.base_dir = Path(self.temp_dir.name)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir()
        self.settings = Settings(
            base_dir=self.base_dir,
            data_dir=self.data_dir,
            db_path=self.data_dir / "test.db",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_inputs(self, modified: date = date(2026, 7, 14)) -> None:
        timestamp = datetime(modified.year, modified.month, modified.day, 18, 0).timestamp()
        for name in REQUIRED_CSV_FILES:
            path = self.data_dir / name
            path.write_text("header\nvalue\n", encoding="utf-8")
            os.utime(path, (timestamp, timestamp))

    def seed_strategy_evidence_session(
        self,
        *,
        signal_date: str,
        review_date: str,
        score_return: float,
        bucketed_return: float,
        advancer_count: int,
        complete: bool = True,
    ) -> tuple[int, int]:
        init_db(self.settings)
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO strategy_pilot_state (
                    pilot_name, status, started_signal_date, momentum_weight,
                    volume_weight, decision_reason
                ) VALUES ('bucketed-default-v1', 'active', '2026-07-01', 0.6, 0.4, 'pilot_active')
                """
            )
            snapshot_id = int(
                connection.execute(
                    """
                    INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
                    VALUES (?, 'daily_csv', 'data')
                    """,
                    (signal_date,),
                ).lastrowid
            )
            connection.executemany(
                """
                INSERT INTO stocks (
                    snapshot_id, ticker, date, open_price, close_price, volume
                ) VALUES (?, ?, ?, 10, ?, 1000)
                """,
                [
                    (
                        snapshot_id,
                        f"S{snapshot_id}{index}",
                        signal_date,
                        11 if index <= advancer_count else 9,
                    )
                    for index in range(1, 5)
                ],
            )
            review_id = int(
                connection.execute(
                    """
                    INSERT INTO review_runs (
                        as_of_date, review_date, avg_return, win_rate, pick_count,
                        wins, momentum_weight, volume_weight, signal_snapshot_id
                    ) VALUES (?, ?, ?, 0.2, 5, 1, 0.6, 0.4, ?)
                    """,
                    (signal_date, review_date, score_return, snapshot_id),
                ).lastrowid
            )
            connection.executemany(
                """
                INSERT INTO candidate_outcomes (
                    review_run_id, signal_date, review_date, ticker,
                    candidate_rank, score, momentum, volume, technical,
                    fundamental, quality, setup_penalty, selected_score_ranked,
                    selected_bucketed, bucketed_bucket, return_pct, won
                ) VALUES (?, ?, ?, ?, ?, ?, 0.7, 0.6, 0.06, 0.01, 0.02, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        review_id,
                        signal_date,
                        review_date,
                        f"C{snapshot_id}{rank}",
                        rank,
                        1.0 - rank / 100,
                        0.0 if rank == 1 else 0.03,
                        1 if rank <= 3 else 0,
                        1 if rank in {2, 4} else 0,
                        "core_momentum" if rank in {2, 4} else None,
                        rank / 100,
                        1 if rank >= 4 else 0,
                    )
                    for rank in range(1, 6)
                ],
            )
            connection.executemany(
                """
                INSERT INTO strategy_pilot_sessions (
                    pilot_name, signal_snapshot_id, signal_date, review_date,
                    strategy, pick_count, evaluated_count, wins, avg_return,
                    is_complete
                ) VALUES ('bucketed-default-v1', ?, ?, ?, ?, 3, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_id,
                        signal_date,
                        review_date,
                        "score_ranked",
                        3 if complete else 2,
                        1 if score_return >= 0.04 else 0,
                        score_return,
                        1 if complete else 0,
                    ),
                    (
                        snapshot_id,
                        signal_date,
                        review_date,
                        "bucketed",
                        3 if complete else 2,
                        1 if bucketed_return >= 0.04 else 0,
                        bucketed_return,
                        1 if complete else 0,
                    ),
                ],
            )
        return snapshot_id, review_id

    def test_latest_review_returns_none_for_empty_database(self) -> None:
        self.assertIsNone(load_latest_review(self.settings))

    def test_latest_picks_returns_none_for_empty_database(self) -> None:
        self.assertIsNone(load_latest_picks(self.settings))

    def test_strategy_evidence_returns_explicit_empty_state(self) -> None:
        evidence = load_strategy_evidence(self.settings)

        self.assertEqual(evidence["status"], "empty")
        self.assertEqual(evidence["window"]["includedReviewCount"], 0)
        self.assertEqual(evidence["comparison"]["status"], "unavailable")
        self.assertEqual(evidence["candidateEvidence"]["status"], "unavailable")
        self.assertEqual(evidence["breadth"]["status"], "unavailable")

    def test_strategy_evidence_is_bounded_and_uses_exact_signal_snapshots(self) -> None:
        self.seed_strategy_evidence_session(
            signal_date="2026-07-01",
            review_date="2026-07-02",
            score_return=0.01,
            bucketed_return=0.02,
            advancer_count=2,
        )
        self.seed_strategy_evidence_session(
            signal_date="2026-07-02",
            review_date="2026-07-03",
            score_return=-0.01,
            bucketed_return=0.03,
            advancer_count=1,
        )
        self.seed_strategy_evidence_session(
            signal_date="2026-07-03",
            review_date="2026-07-06",
            score_return=0.80,
            bucketed_return=-0.80,
            advancer_count=4,
        )
        with connect(self.settings) as connection:
            repair_snapshot_id = int(
                connection.execute(
                    """
                    INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
                    VALUES ('2026-07-02', 'repair', 'repair')
                    """
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO stocks (
                    snapshot_id, ticker, date, open_price, close_price, volume
                ) VALUES (?, 'LATER', '2026-07-02', 10, 20, 1000)
                """,
                (repair_snapshot_id,),
            )

        evidence = load_strategy_evidence(
            self.settings,
            window=5,
            end_review_date=date(2026, 7, 3),
        )

        self.assertEqual(evidence["window"]["includedReviewCount"], 2)
        self.assertEqual(evidence["window"]["endReviewDate"], "2026-07-03")
        self.assertEqual(evidence["candidateEvidence"]["candidateCount"], 10)
        self.assertEqual(evidence["candidateEvidence"]["capturedReviewCount"], 2)
        self.assertEqual(evidence["candidateEvidence"]["setupPenalty"]["penalized"]["count"], 8)
        self.assertEqual(evidence["candidateEvidence"]["setupPenalty"]["unpenalized"]["count"], 2)
        self.assertEqual(evidence["comparison"]["completePairedSessions"], 2)
        self.assertEqual(evidence["comparison"]["bucketedSessionWins"], 2)
        self.assertEqual(evidence["pilot"]["completedSessions"], 2)
        self.assertEqual(evidence["breadth"]["averageAdvancerRatio"], 0.375)
        self.assertEqual(
            [row["advancerRatio"] for row in evidence["breadth"]["sessions"]],
            [0.5, 0.25],
        )

    def test_strategy_evidence_keeps_incomplete_pairs_visible(self) -> None:
        self.seed_strategy_evidence_session(
            signal_date="2026-07-01",
            review_date="2026-07-02",
            score_return=0.01,
            bucketed_return=0.02,
            advancer_count=2,
            complete=False,
        )

        evidence = load_strategy_evidence(self.settings, window=5)

        self.assertEqual(evidence["comparison"]["status"], "partial")
        self.assertEqual(evidence["comparison"]["completePairedSessions"], 0)
        self.assertEqual(evidence["comparison"]["incompletePairedSessions"], 1)
        self.assertEqual(evidence["pilot"]["completedSessions"], 0)

    def test_strategy_evidence_uses_signal_date_for_pilot_start_boundary(self) -> None:
        self.seed_strategy_evidence_session(
            signal_date="2026-07-01",
            review_date="2026-07-02",
            score_return=0.01,
            bucketed_return=0.02,
            advancer_count=2,
        )
        with connect(self.settings) as connection:
            connection.execute(
                """
                UPDATE strategy_pilot_state
                SET started_signal_date = '2026-07-02'
                WHERE pilot_name = 'bucketed-default-v1'
                """
            )

        evidence = load_strategy_evidence(
            self.settings,
            window=5,
            end_review_date=date(2026, 7, 2),
        )

        self.assertEqual(evidence["window"]["endReviewDate"], "2026-07-02")
        self.assertEqual(evidence["pilot"]["status"], "not_started")
        self.assertEqual(evidence["pilot"]["selectedStrategy"], "score_ranked")
        self.assertEqual(evidence["pilot"]["decisionReason"], "pilot_not_started_as_of_window")

    def test_strategy_evidence_marks_missing_pilot_sessions_as_unpaired(self) -> None:
        self.seed_strategy_evidence_session(
            signal_date="2026-07-01",
            review_date="2026-07-02",
            score_return=0.01,
            bucketed_return=0.02,
            advancer_count=2,
        )
        missing_snapshot_id, _ = self.seed_strategy_evidence_session(
            signal_date="2026-07-02",
            review_date="2026-07-03",
            score_return=0.02,
            bucketed_return=0.03,
            advancer_count=3,
        )
        with connect(self.settings) as connection:
            connection.execute(
                "DELETE FROM strategy_pilot_sessions WHERE signal_snapshot_id = ?",
                (missing_snapshot_id,),
            )

        evidence = load_strategy_evidence(self.settings, window=5)

        self.assertEqual(evidence["comparison"]["status"], "partial")
        self.assertEqual(evidence["comparison"]["completePairedSessions"], 1)
        self.assertEqual(evidence["comparison"]["unpairedSessions"], 1)
        self.assertEqual(len(evidence["comparison"]["sessions"]), 2)

    def test_strategy_evidence_rejects_unsupported_windows(self) -> None:
        with self.assertRaisesRegex(RoutineRequestError, "5, 10, 20, or all"):
            load_strategy_evidence(self.settings, window=7)

    def test_strategy_playback_uses_review_owned_rows_and_exact_snapshot(self) -> None:
        snapshot_id, review_id = self.seed_strategy_evidence_session(
            signal_date="2026-07-01",
            review_date="2026-07-02",
            score_return=0.05,
            bucketed_return=0.02,
            advancer_count=2,
        )
        with connect(self.settings) as connection:
            connection.execute(
                """
                UPDATE review_runs
                SET strategy_version = 'bucketed-default-v1:bucketed', weight_date = '2026-07-01'
                WHERE id = ?
                """,
                (review_id,),
            )
            connection.executemany(
                """
                INSERT INTO review_pick_results (
                    review_run_id, ticker, score, open_price, close_price, return_pct, won
                ) VALUES (?, ?, ?, 10, ?, ?, ?)
                """,
                [
                    (review_id, f"C{snapshot_id}2", 0.98, 10.5, 0.05, 1),
                    (review_id, f"C{snapshot_id}4", 0.96, 9.8, -0.02, 0),
                ],
            )
            connection.executemany(
                """
                INSERT INTO picks (
                    snapshot_id, date, ticker, score, kap, momentum, volume,
                    risk, horizon, selection_bucket
                ) VALUES (?, '2026-07-01', ?, ?, 0, 0.7, 0.6, 'high', 'intraday', ?)
                """,
                [
                    (snapshot_id, f"C{snapshot_id}2", 0.98, "core_momentum"),
                    (snapshot_id, f"C{snapshot_id}4", 0.96, "core_momentum"),
                ],
            )
            later_snapshot_id = connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
                VALUES ('2026-07-01', 'repair', 'repair')
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO stocks (snapshot_id, ticker, date, open_price, close_price, volume)
                VALUES (?, 'LATER', '2026-07-01', 10, 20, 1000)
                """,
                (later_snapshot_id,),
            )
            connection.execute(
                """
                INSERT INTO candidate_outcomes (
                    review_run_id, signal_date, review_date, ticker, candidate_rank,
                    score, momentum, volume, technical, fundamental, quality,
                    setup_penalty, selected_score_ranked, selected_bucketed,
                    bucketed_bucket, return_pct, won
                ) VALUES (?, '2026-07-01', '2026-07-02', 'UNRELATED', 99,
                    0.1, 0, 0, 0, 0, 0, 0, 0, 0, NULL, 0, 0)
                """,
                (review_id,),
            )

        playback = load_strategy_playback(self.settings, review_id)

        assert playback is not None
        self.assertEqual(playback["signal"]["snapshotId"], snapshot_id)
        self.assertEqual(playback["signal"]["source"], "daily_csv")
        self.assertEqual(playback["signal"]["universeCount"], 4)
        self.assertEqual(playback["signal"]["advancerRatio"], 0.5)
        self.assertEqual(playback["strategy"]["selectedStrategy"], "bucketed")
        self.assertEqual(playback["basket"]["attributionStatus"], "available")
        self.assertEqual(
            [row["candidateRank"] for row in playback["basket"]["picks"]],
            [2, 4],
        )
        self.assertEqual(playback["basket"]["picks"][0]["selectionBucket"], "core_momentum")
        self.assertEqual(len(playback["pilotComparison"]["arms"]), 2)

    def test_strategy_playback_preserves_legacy_unavailable_states(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            review_id = int(
                connection.execute(
                    """
                    INSERT INTO review_runs (
                        as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                        momentum_weight, volume_weight
                    ) VALUES ('2026-06-01', '2026-06-02', 0, 0, 1, 0, 0.6, 0.4)
                    """
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO review_pick_results (
                    review_run_id, ticker, score, open_price, close_price, return_pct, won
                ) VALUES (?, 'LEGACY', 0.5, 10, 9, -0.1, 0)
                """,
                (review_id,),
            )

        playback = load_strategy_playback(self.settings, review_id)

        assert playback is not None
        self.assertEqual(playback["signal"]["status"], "unavailable")
        self.assertEqual(playback["basket"]["status"], "available")
        self.assertEqual(playback["basket"]["attributionStatus"], "unavailable")
        self.assertIsNone(playback["basket"]["picks"][0]["signals"])
        self.assertIsNone(load_strategy_playback(self.settings, 999))

    def test_latest_picks_uses_newest_snapshot_and_persisted_portfolio(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            older_id = connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, imported_at, source_label, source_dir)
                VALUES ('2026-07-17', '2026-07-17 16:00:00', 'daily_csv', 'data')
                """
            ).lastrowid
            latest_id = connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, imported_at, source_label, source_dir)
                VALUES ('2026-07-22', '2026-07-22 16:10:04', 'daily_csv', 'data')
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO picks (
                    snapshot_id, date, ticker, score, kap, momentum, volume,
                    risk, horizon, selection_bucket
                ) VALUES (?, '2026-07-17', 'OLD', 1.1, 0, 1, 1, 'high', 'intraday', 'score_ranked')
                """,
                (older_id,),
            )
            connection.executemany(
                """
                INSERT INTO picks (
                    snapshot_id, date, ticker, score, kap, momentum, volume,
                    risk, horizon, selection_bucket
                ) VALUES (?, '2026-07-22', ?, ?, 0, ?, ?, 'high', 'intraday', 'score_ranked')
                """,
                [
                    (latest_id, "NEW2", 0.9, 0.8, 0.7),
                    (latest_id, "NEW1", 1.0, 0.9, 0.8),
                ],
            )

        dashboard = load_latest_picks(self.settings)

        self.assertIsNotNone(dashboard)
        assert dashboard is not None
        self.assertEqual(dashboard["snapshot"]["id"], latest_id)
        self.assertEqual(dashboard["signalDate"], "2026-07-22")
        self.assertEqual(dashboard["tradeDate"], "2026-07-23")
        self.assertEqual([pick["ticker"] for pick in dashboard["picks"]], ["NEW1", "NEW2"])

    def test_latest_picks_ignores_newer_price_only_snapshot(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            picks_snapshot_id = connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, imported_at, source_label, source_dir)
                VALUES ('2026-07-22', '2026-07-22 16:10:04', 'daily_csv', 'data')
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO picks (
                    snapshot_id, date, ticker, score, kap, momentum, volume,
                    risk, horizon, selection_bucket
                ) VALUES (?, '2026-07-22', 'PICK', 1.0, 0, 0.9, 0.8,
                    'high', 'intraday', 'score_ranked')
                """,
                (picks_snapshot_id,),
            )
            repair_snapshot_id = connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, imported_at, source_label, source_dir)
                VALUES ('2026-07-21', '2026-07-23 10:00:00', 'yahoo_history_browser', 'repair.json')
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO stocks (
                    snapshot_id, ticker, date, open_price, close_price, volume
                ) VALUES (?, 'PICK', '2026-07-21', 10, 11, 1000)
                """,
                (repair_snapshot_id,),
            )

        dashboard = load_latest_picks(self.settings)

        self.assertIsNotNone(dashboard)
        assert dashboard is not None
        self.assertEqual(dashboard["snapshot"]["id"], picks_snapshot_id)
        self.assertEqual([pick["ticker"] for pick in dashboard["picks"]], ["PICK"])

    def test_http_health_and_latest_picks_use_real_sqlite_fixture(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            picks_snapshot_id = connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, imported_at, source_label, source_dir)
                VALUES ('2026-07-22', '2026-07-22 16:10:04', 'daily_csv', 'data')
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO picks (
                    snapshot_id, date, ticker, score, kap, momentum, volume,
                    risk, horizon, selection_bucket
                ) VALUES (?, '2026-07-22', 'PICK', 1.0, 0, 0.9, 0.8,
                    'high', 'intraday', 'score_ranked')
                """,
                (picks_snapshot_id,),
            )
            connection.execute(
                """
                INSERT INTO snapshot_runs (snapshot_date, imported_at, source_label, source_dir)
                VALUES ('2026-07-21', '2026-07-23 10:00:00',
                    'yahoo_history_browser', 'repair.json')
                """
            )
            playback_review_id = int(
                connection.execute(
                    """
                    INSERT INTO review_runs (
                        as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                        momentum_weight, volume_weight, signal_snapshot_id
                    ) VALUES ('2026-07-22', '2026-07-23', 0.05, 1, 1, 1, 0.6, 0.4, ?)
                    """,
                    (picks_snapshot_id,),
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO review_pick_results (
                    review_run_id, ticker, score, open_price, close_price, return_pct, won
                ) VALUES (?, 'PICK', 1, 10, 10.5, 0.05, 1)
                """,
                (playback_review_id,),
            )

        server = RoutineApiServer(("127.0.0.1", 0), self.settings, self.data_dir)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_port)
            with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
                health = json.load(response)
            with urlopen(f"http://127.0.0.1:{port}/api/picks/latest", timeout=5) as response:
                picks = json.load(response)
            with urlopen(f"http://127.0.0.1:{port}/api/strategy-evidence?window=5", timeout=5) as response:
                strategy_evidence = json.load(response)
            with urlopen(f"http://127.0.0.1:{port}/api/strategy-playback/{playback_review_id}", timeout=5) as response:
                playback = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(health, {"ok": True, "apiPort": port})
        self.assertEqual(picks["dashboard"]["snapshot"]["id"], picks_snapshot_id)
        self.assertEqual([item["ticker"] for item in picks["dashboard"]["picks"]], ["PICK"])
        self.assertEqual(strategy_evidence["evidence"]["status"], "available")
        self.assertEqual(strategy_evidence["evidence"]["window"]["requested"], "5")
        self.assertEqual(playback["playback"]["review"]["id"], playback_review_id)
        self.assertEqual(playback["playback"]["basket"]["picks"][0]["ticker"], "PICK")

    def test_latest_review_returns_newest_persisted_run_and_outcomes(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            older_id = connection.execute(
                """
                INSERT INTO review_runs (
                    as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                    momentum_weight, volume_weight
                ) VALUES ('2026-07-17', '2026-07-20', 0.01, 0.2, 5, 1, 0.6, 0.4)
                """
            ).lastrowid
            latest_id = connection.execute(
                """
                INSERT INTO review_runs (
                    as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                    momentum_weight, volume_weight
                ) VALUES ('2026-07-14', '2026-07-16', -0.02, 0.0, 2, 0, 0.6, 0.4)
                """
            ).lastrowid
            connection.executemany(
                """
                INSERT INTO review_pick_results (
                    review_run_id, ticker, score, open_price, close_price, return_pct, won
                ) VALUES (?, ?, ?, 10.0, 9.8, ?, 0)
                """,
                [(latest_id, "LOW", 0.5, -0.02), (latest_id, "HIGH", 0.9, -0.01)],
            )

        review = load_latest_review(self.settings)

        self.assertIsNotNone(review)
        assert review is not None
        self.assertNotEqual(review["id"], older_id)
        self.assertEqual(review["id"], latest_id)
        self.assertEqual(review["signalDate"], "2026-07-14")
        self.assertEqual(review["reviewDate"], "2026-07-16")
        self.assertEqual(review["minimumWinReturn"], 0.04)
        self.assertEqual([outcome["ticker"] for outcome in review["outcomes"]], ["HIGH", "LOW"])
        self.assertEqual(review["missedMoversStatus"], "not_captured")
        self.assertEqual(review["missedMovers"], [])

        history = load_review_history(self.settings)
        self.assertEqual([item["id"] for item in history], [latest_id, older_id])
        self.assertEqual(history[0]["wins"], 0)
        self.assertEqual(history[0]["pickCount"], 2)
        self.assertNotIn("outcomes", history[0])

        selected = load_review_by_id(self.settings, int(older_id))
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["signalDate"], "2026-07-17")
        self.assertEqual(selected["outcomes"], [])
        self.assertEqual(selected["missedMoversStatus"], "not_captured")
        self.assertIsNone(load_review_by_id(self.settings, 999))

    def test_review_detail_serializes_captured_missed_mover_evidence(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            review_id = connection.execute(
                """
                INSERT INTO review_runs (
                    as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                    momentum_weight, volume_weight, missed_movers_captured
                ) VALUES ('2026-07-22', '2026-07-23', 0.01, 0.2, 5, 1, 0.6, 0.4, 1)
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO review_missed_mover_results (
                    review_run_id, mover_order, ticker, classification, reason,
                    close_change_return, data_status, candidate_rank, selection_note,
                    selection_bucket, momentum, volume, technical, fundamental,
                    quality, setup_penalty, ma_trend, liquidity, total_boost,
                    net_adjustment
                ) VALUES (
                    ?, 1, 'MISSED', 'actionable', 'not_selected_by_score', 0.08,
                    'ranked_candidate', 6, 'below_top_pick_cutoff', 'score_ranked',
                    0.7, 0.6, 0.04, 0.01, 0.02, 0.03, 1.0, 0.9, 0.07, 0.04
                )
                """,
                (review_id,),
            )

        review = load_review_by_id(self.settings, int(review_id))

        assert review is not None
        self.assertEqual(review["missedMoversStatus"], "captured")
        self.assertEqual(len(review["missedMovers"]), 1)
        mover = review["missedMovers"][0]
        self.assertEqual(mover["ticker"], "MISSED")
        self.assertEqual(mover["classification"], "actionable")
        self.assertEqual(mover["returnPct"], 0.08)
        self.assertEqual(mover["attribution"]["candidateRank"], 6)
        self.assertEqual(mover["attribution"]["signals"]["setupPenalty"], 0.03)
        self.assertEqual(mover["attribution"]["adjustments"]["netAdjustment"], 0.04)

    def test_review_detail_distinguishes_captured_empty_evidence(self) -> None:
        init_db(self.settings)
        with connect(self.settings) as connection:
            review_id = connection.execute(
                """
                INSERT INTO review_runs (
                    as_of_date, review_date, avg_return, win_rate, pick_count, wins,
                    momentum_weight, volume_weight, missed_movers_captured
                ) VALUES ('2026-07-22', '2026-07-23', 0.01, 0.2, 5, 1, 0.6, 0.4, 1)
                """
            ).lastrowid

        review = load_review_by_id(self.settings, int(review_id))

        assert review is not None
        self.assertEqual(review["missedMoversStatus"], "captured")
        self.assertEqual(review["missedMovers"], [])

    def test_preview_resolves_recurring_holiday_to_previous_session(self) -> None:
        self.write_inputs()

        preview = build_routine_preview(
            self.settings,
            "2026-07-15",
            today=date(2026, 7, 18),
        )

        self.assertEqual(preview["resolvedSignalDate"], "2026-07-14")
        self.assertEqual(preview["targetTradeDate"], "2026-07-16")
        self.assertFalse(preview["requestedWasTradingSession"])
        self.assertTrue(preview["ready"])
        self.assertIn("not an open trading session", preview["warnings"][0])

    def test_preview_blocks_missing_and_stale_inputs(self) -> None:
        self.write_inputs(modified=date(2026, 7, 13))
        (self.data_dir / "temel.csv").unlink()

        preview = build_routine_preview(
            self.settings,
            "2026-07-14",
            today=date(2026, 7, 18),
        )

        self.assertFalse(preview["ready"])
        self.assertEqual(
            {item["status"] for item in preview["files"]},
            {"stale", "missing"},
        )
        self.assertTrue(any("Missing required input" in issue for issue in preview["blockingIssues"]))

    def test_preview_blocks_future_signal_date(self) -> None:
        self.write_inputs(modified=date(2026, 7, 20))

        preview = build_routine_preview(
            self.settings,
            "2026-07-20",
            today=date(2026, 7, 18),
        )

        self.assertFalse(preview["ready"])
        self.assertIn("Future signal dates cannot be run.", preview["blockingIssues"])

    def test_execute_requires_current_confirmation_token(self) -> None:
        self.write_inputs()
        preview = build_routine_preview(
            self.settings,
            "2026-07-14",
            today=date(2026, 7, 18),
        )
        (self.data_dir / "fiyat.csv").write_text("changed\ncontent\n", encoding="utf-8")

        with self.assertRaisesRegex(RoutineRequestError, "preview is stale"):
            execute_routine(
                self.settings,
                "2026-07-14",
                preview["confirmationToken"],
                True,
                today=date(2026, 7, 18),
            )

    def test_execute_reports_persisted_snapshot_and_pick_count(self) -> None:
        self.write_inputs()
        preview = build_routine_preview(
            self.settings,
            "2026-07-14",
            today=date(2026, 7, 18),
        )

        def fake_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            init_db(self.settings)
            with connect(self.settings) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO snapshot_runs (snapshot_date, source_label, source_dir)
                    VALUES ('2026-07-14', 'daily_csv', 'data')
                    """
                )
                snapshot_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO picks (
                        snapshot_id, date, ticker, score, kap, momentum, volume,
                        risk, horizon, selection_bucket
                    ) VALUES (?, '2026-07-14', 'TEST', 1.0, 0.0, 0.6, 0.4, 'low', 'intraday', 'score_ranked')
                    """,
                    (snapshot_id,),
                )
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="routine ok", stderr="")

        result = execute_routine(
            self.settings,
            "2026-07-14",
            preview["confirmationToken"],
            True,
            today=date(2026, 7, 18),
            runner=fake_runner,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["snapshotId"], 1)
        self.assertEqual(result["pickCount"], 1)
        self.assertIsNone(result["reviewRunId"])
        self.assertEqual(result["targetTradeDate"], "2026-07-16")

    def test_execute_reports_process_start_failure(self) -> None:
        self.write_inputs()
        preview = build_routine_preview(
            self.settings,
            "2026-07-14",
            today=date(2026, 7, 18),
        )

        def failing_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise OSError("python unavailable")

        with self.assertRaisesRegex(RoutineRequestError, "could not be started"):
            execute_routine(
                self.settings,
                "2026-07-14",
                preview["confirmationToken"],
                True,
                today=date(2026, 7, 18),
                runner=failing_runner,
            )


if __name__ == "__main__":
    unittest.main()
