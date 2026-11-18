"""Borsa İstanbul equity-market (Pay Piyasası) trading calendar.

Fixed national holidays fall on the same month and day every year, so they
are recurring rules. Variable religious holidays (Ramazan and Kurban Bayramı,
and their half-day eves) and any ad-hoc closures move every year, so they are
exact dates per year, copied from the Borsa İstanbul annual holiday
announcement. They must never be modelled as month/day rules.

2026 comes from Borsa İstanbul notice 41625 dated 2025-12-04, appendix EK-3
"Pay Piyasası 2026 Yılı Tatil Tablosu". A year without a confirmed entry
treats its religious-holiday closures and half days as open full sessions;
``calendar_coverage_warnings`` reports such years so callers can surface them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta


RECURRING_MARKET_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 1),  # New Year's Day
        (4, 23),  # National Sovereignty and Children's Day
        (5, 1),  # Labour and Solidarity Day
        (5, 19),  # Commemoration of Atatürk, Youth and Sports Day
        (7, 15),  # Democracy and National Unity Day
        (8, 30),  # Victory Day
        (10, 29),  # Republic Day
    }
)

RECURRING_HALF_DAY_SESSIONS: frozenset[tuple[int, int]] = frozenset(
    {
        (10, 28),  # Republic Day eve, statutory half day
    }
)


@dataclass(frozen=True)
class ConfirmedYear:
    """Variable-date equity-market closures and half days for one year."""

    source: str
    closures: frozenset[date]
    half_days: frozenset[date]


CONFIRMED_VARIABLE_CALENDAR: dict[int, ConfirmedYear] = {
    2026: ConfirmedYear(
        source=(
            "Borsa İstanbul notice 41625 (2025-12-04), "
            "EK-3 Pay Piyasası 2026 Yılı Tatil Tablosu"
        ),
        closures=frozenset(
            {
                date(2026, 3, 20),  # Ramazan Bayramı
                date(2026, 5, 27),  # Kurban Bayramı
                date(2026, 5, 28),  # Kurban Bayramı
                date(2026, 5, 29),  # Kurban Bayramı
            }
        ),
        half_days=frozenset(
            {
                date(2026, 3, 19),  # Ramazan Bayramı arife
                date(2026, 5, 26),  # Kurban Bayramı arife
            }
        ),
    ),
}


def validate_confirmed_calendar(calendar: Mapping[int, ConfirmedYear]) -> None:
    """Reject confirmed entries that are misfiled, contradictory, or redundant.

    A confirmed date must belong to its year, must not be both a closure and a
    half day, must fall on a weekday, and must not restate or contradict a
    recurring national-holiday closure.
    """
    for year, confirmed in calendar.items():
        misplaced = sorted(day for day in confirmed.closures | confirmed.half_days if day.year != year)
        if misplaced:
            raise ValueError(
                f"Confirmed BIST calendar for {year} lists dates from another year: "
                + ", ".join(day.isoformat() for day in misplaced)
            )
        overlap = sorted(confirmed.closures & confirmed.half_days)
        if overlap:
            raise ValueError(
                f"Confirmed BIST calendar for {year} marks dates as both a closure and a half day: "
                + ", ".join(day.isoformat() for day in overlap)
            )
        weekend = sorted(day for day in confirmed.closures | confirmed.half_days if day.weekday() >= 5)
        if weekend:
            raise ValueError(
                f"Confirmed BIST calendar for {year} lists weekend dates: "
                + ", ".join(day.isoformat() for day in weekend)
            )
        recurring_closures = sorted(
            day for day in confirmed.closures if (day.month, day.day) in RECURRING_MARKET_HOLIDAYS
        )
        if recurring_closures:
            raise ValueError(
                f"Confirmed BIST calendar for {year} repeats recurring holiday closures: "
                + ", ".join(day.isoformat() for day in recurring_closures)
            )
        recurring_half_days = sorted(
            day for day in confirmed.half_days if (day.month, day.day) in RECURRING_MARKET_HOLIDAYS
        )
        if recurring_half_days:
            raise ValueError(
                f"Confirmed BIST calendar for {year} marks recurring holiday closures as half days: "
                + ", ".join(day.isoformat() for day in recurring_half_days)
            )


validate_confirmed_calendar(CONFIRMED_VARIABLE_CALENDAR)


def _confirmed_year(day: date) -> ConfirmedYear | None:
    return CONFIRMED_VARIABLE_CALENDAR.get(day.year)


def is_trading_session(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    if (day.month, day.day) in RECURRING_MARKET_HOLIDAYS:
        return False
    confirmed = _confirmed_year(day)
    return confirmed is None or day not in confirmed.closures


def is_half_day_session(day: date) -> bool:
    if not is_trading_session(day):
        return False
    if (day.month, day.day) in RECURRING_HALF_DAY_SESSIONS:
        return True
    confirmed = _confirmed_year(day)
    return confirmed is not None and day in confirmed.half_days


def previous_trading_session(day: date) -> date:
    previous = day - timedelta(days=1)
    while not is_trading_session(previous):
        previous -= timedelta(days=1)
    return previous


def next_trading_session(day: date) -> date:
    next_day = day + timedelta(days=1)
    while not is_trading_session(next_day):
        next_day += timedelta(days=1)
    return next_day


def calendar_coverage_warnings(*days: date) -> list[str]:
    """One warning per distinct year among ``days`` with no confirmed entry."""
    return [
        (
            f"No confirmed variable-date BIST holidays are recorded for {year}; "
            "religious-holiday closures and half days that year are treated as open full sessions "
            "until stock_expert/trading_calendar.py is updated from the Borsa Istanbul holiday announcement."
        )
        for year in sorted({day.year for day in days})
        if year not in CONFIRMED_VARIABLE_CALENDAR
    ]
