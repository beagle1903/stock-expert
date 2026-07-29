from __future__ import annotations

from dataclasses import dataclass


PILOT_NAME = "bucketed-default-v1"
PILOT_SESSION_TARGET = 10
PILOT_MIN_BUCKETED_WINS = 6
PILOT_PROMOTION_EDGE = 0.03
PILOT_ROLLBACK_EDGE = -0.03


@dataclass(frozen=True)
class PilotEvaluation:
    status: str
    completed_sessions: int
    bucketed_session_wins: int
    score_compounded_return: float
    bucketed_compounded_return: float
    compounded_edge: float
    decision_reason: str


def operational_strategy(status: str | None) -> str:
    if status in {"rolled_back", "failed"}:
        return "score_ranked"
    return "bucketed"


def evaluate_pilot_sessions(rows: list[object]) -> PilotEvaluation:
    sessions: dict[int, dict[str, dict[str, object]]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        snapshot_id = int(row["signal_snapshot_id"])
        sessions.setdefault(snapshot_id, {})[str(row["strategy"])] = row

    score_growth = 1.0
    bucketed_growth = 1.0
    completed_sessions = 0
    bucketed_session_wins = 0
    status = "active"
    reason = "pilot_active"

    for snapshot_id in sorted(sessions):
        pair = sessions[snapshot_id]
        score_row = pair.get("score_ranked")
        bucketed_row = pair.get("bucketed")
        if score_row is None or bucketed_row is None:
            continue
        if not bool(score_row["is_complete"]) or not bool(bucketed_row["is_complete"]):
            continue

        score_return = float(score_row["avg_return"])
        bucketed_return = float(bucketed_row["avg_return"])
        score_growth *= 1.0 + score_return
        bucketed_growth *= 1.0 + bucketed_return
        completed_sessions += 1
        if bucketed_return > score_return:
            bucketed_session_wins += 1

        edge = (bucketed_growth - 1.0) - (score_growth - 1.0)
        if edge <= PILOT_ROLLBACK_EDGE:
            status = "rolled_back"
            reason = "bucketed_trailing_guardrail"
            break
        if completed_sessions == PILOT_SESSION_TARGET:
            if (
                bucketed_session_wins >= PILOT_MIN_BUCKETED_WINS
                and edge >= PILOT_PROMOTION_EDGE
            ):
                status = "promoted"
                reason = "promotion_thresholds_met"
            else:
                status = "failed"
                reason = "promotion_thresholds_not_met"
            break

    score_compounded_return = score_growth - 1.0
    bucketed_compounded_return = bucketed_growth - 1.0
    return PilotEvaluation(
        status=status,
        completed_sessions=completed_sessions,
        bucketed_session_wins=bucketed_session_wins,
        score_compounded_return=round(score_compounded_return, 6),
        bucketed_compounded_return=round(bucketed_compounded_return, 6),
        compounded_edge=round(bucketed_compounded_return - score_compounded_return, 6),
        decision_reason=reason,
    )
