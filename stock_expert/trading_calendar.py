from __future__ import annotations

from datetime import date, timedelta


USER_CONFIRMED_MARKET_HOLIDAYS = {
    # Exact exchange-closed dates confirmed by the user; variable-date
    # holidays must not be modeled as recurring month/day rules.
    date(2026, 5, 1),
    date(2026, 5, 19),
    date(2026, 5, 27),
    date(2026, 5, 28),
    date(2026, 5, 29),
}

# July 15, Democracy and National Unity Day, is an annual BIST closure.
RECURRING_MARKET_HOLIDAYS = {
    (7, 15),
}


def is_trading_session(day: date) -> bool:
    return (
        day.weekday() < 5
        and day not in USER_CONFIRMED_MARKET_HOLIDAYS
        and (day.month, day.day) not in RECURRING_MARKET_HOLIDAYS
    )


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
