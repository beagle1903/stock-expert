"""Signal-window coverage: does a signal read consecutive trading sessions?

Signal components index price bars by position over the newest operational
snapshot dates, not over trading sessions. After an import gap (or a snapshot
stored under a weekend or holiday date) those positions silently span missing
sessions. This module only detects and describes that gap so it can be
recorded as degraded evidence with the signal publication. It never changes a
score, the exposure, or the selection.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from stock_expert.trading_calendar import is_trading_session


# Snapshot dates each signal component reads, newest first, ending on the
# signal date. Keep these equal to the real lookbacks; tests/test_signal_window.py
# pins them so a lookback change without an update here breaks a test.
SIGNAL_WINDOW_COMPONENTS: dict[str, int] = {
    # signals.compute_momentum: compute_medium_momentum (6 bars) is the
    # longest of compute_short_momentum (4) and compute_ma_trend (5).
    "momentum": 6,
    # signals.compute_volume_spike: the signal-date bar against the 4 before it.
    "volume": 5,
    # services._compute_ranked_candidate_rows fetches
    # get_recent_price_history(..., bars=4) for prior_close_returns_pct and
    # apply_fade_then_rechase_penalty.
    "fade_then_rechase": 4,
}

SIGNAL_WINDOW_BARS = max(SIGNAL_WINDOW_COMPONENTS.values())

STATUS_CONTIGUOUS = "contiguous"
STATUS_GAP = "gap"


@dataclass(frozen=True)
class SignalWindowCoverage:
    signal_date: date
    status: str
    window_bars: int
    window_start: date
    missing_sessions: tuple[date, ...]
    non_session_dates: tuple[date, ...]
    affected_components: tuple[str, ...]

    @property
    def window_end(self) -> date:
        return self.signal_date

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SignalWindowCoverage:
        """Rebuild coverage from ``to_payload`` output or a stored row."""
        return cls(
            signal_date=date.fromisoformat(str(payload["window_end"])),
            status=str(payload["status"]),
            window_bars=int(payload["window_bars"]),
            window_start=date.fromisoformat(str(payload["window_start"])),
            missing_sessions=tuple(date.fromisoformat(str(day)) for day in payload["missing_sessions"]),
            non_session_dates=tuple(date.fromisoformat(str(day)) for day in payload["non_session_dates"]),
            affected_components=tuple(str(component) for component in payload["affected_components"]),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "window_bars": self.window_bars,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "missing_sessions": [day.isoformat() for day in self.missing_sessions],
            "non_session_dates": [day.isoformat() for day in self.non_session_dates],
            "affected_components": list(self.affected_components),
        }


def _days_between(start: date, end: date) -> Iterable[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def assess_signal_window(
    signal_date: date,
    snapshot_dates_desc: list[date],
) -> SignalWindowCoverage | None:
    """Describe the trading sessions the signal components read for ``signal_date``.

    ``snapshot_dates_desc`` holds the operational snapshot dates on or before
    ``signal_date``, newest first. Returns None when there is no snapshot for
    ``signal_date`` itself, because no basket can be published then.
    """
    dates = sorted({day for day in snapshot_dates_desc if day <= signal_date}, reverse=True)
    if not dates or dates[0] != signal_date:
        return None
    window = dates[:SIGNAL_WINDOW_BARS]
    window_start = window[-1]
    window_dates = set(window)
    missing_sessions = tuple(
        day
        for day in _days_between(window_start, signal_date)
        if is_trading_session(day) and day not in window_dates
    )
    non_session_dates = tuple(sorted(day for day in window if not is_trading_session(day)))
    affected_components = tuple(
        component
        for component, bars in SIGNAL_WINDOW_COMPONENTS.items()
        if any(window[: bars][-1] <= day for day in missing_sessions)
        or any(day in non_session_dates for day in window[:bars])
    )
    return SignalWindowCoverage(
        signal_date=signal_date,
        status=STATUS_GAP if missing_sessions or non_session_dates else STATUS_CONTIGUOUS,
        window_bars=len(window),
        window_start=window_start,
        missing_sessions=missing_sessions,
        non_session_dates=non_session_dates,
        affected_components=affected_components,
    )


def _date_list(days: tuple[date, ...]) -> str:
    return ", ".join(day.isoformat() for day in days)


def signal_window_warning(coverage: SignalWindowCoverage | None) -> str | None:
    """One ASCII sentence for a gapped window, or None when it is contiguous."""
    if coverage is None or coverage.status != STATUS_GAP:
        return None
    findings = []
    if coverage.missing_sessions:
        findings.append(f"spans missing trading session(s) {_date_list(coverage.missing_sessions)}")
    if coverage.non_session_dates:
        findings.append(f"includes non-session snapshot date(s) {_date_list(coverage.non_session_dates)}")
    components = ", ".join(coverage.affected_components)
    return (
        f"Signal window {coverage.window_start.isoformat()} to {coverage.window_end.isoformat()} "
        f"{' and '.join(findings)}; {components} read non-contiguous bars. Scores are unchanged."
    )
