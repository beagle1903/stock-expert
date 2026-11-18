from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_expert.trading_calendar import (
    CONFIRMED_VARIABLE_CALENDAR,
    ConfirmedYear,
    calendar_coverage_warnings,
    is_half_day_session,
    is_trading_session,
    next_trading_session,
    previous_trading_session,
    validate_confirmed_calendar,
)


# Borsa İstanbul notice 41625 (2025-12-04), EK-3: every weekday the equity
# market is closed in 2026.
CLOSED_WEEKDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 3, 20),
    date(2026, 4, 23),
    date(2026, 5, 1),
    date(2026, 5, 19),
    date(2026, 5, 27),
    date(2026, 5, 28),
    date(2026, 5, 29),
    date(2026, 7, 15),
    date(2026, 10, 29),
}


class TradingSessionTests(unittest.TestCase):
    def test_2026_weekday_closures_match_the_exchange_table_exactly(self) -> None:
        day = date(2026, 1, 1)
        closed: set[date] = set()
        while day.year == 2026:
            if day.weekday() < 5 and not is_trading_session(day):
                closed.add(day)
            day += timedelta(days=1)

        self.assertEqual(closed, CLOSED_WEEKDAYS_2026)

    def test_weekends_are_not_sessions(self) -> None:
        self.assertFalse(is_trading_session(date(2026, 4, 25)))
        self.assertFalse(is_trading_session(date(2026, 4, 26)))

    def test_sunday_victory_day_is_closed_and_the_following_monday_is_open(self) -> None:
        self.assertFalse(is_trading_session(date(2026, 8, 30)))
        self.assertTrue(is_trading_session(date(2026, 8, 31)))

    def test_monday_before_kurban_arife_is_a_normal_session(self) -> None:
        self.assertTrue(is_trading_session(date(2026, 5, 25)))
        self.assertFalse(is_half_day_session(date(2026, 5, 25)))


class TradingSessionNavigationTests(unittest.TestCase):
    def assert_neighbours(self, before: date, after: date) -> None:
        with self.subTest(before=before.isoformat(), after=after.isoformat()):
            self.assertEqual(next_trading_session(before), after)
            self.assertEqual(previous_trading_session(after), before)

    def test_next_and_previous_skip_weekends(self) -> None:
        self.assertEqual(next_trading_session(date(2026, 4, 24)), date(2026, 4, 27))
        self.assertEqual(previous_trading_session(date(2026, 4, 27)), date(2026, 4, 24))

    def test_navigation_skips_every_2026_closure_in_both_directions(self) -> None:
        cases = [
            (date(2025, 12, 31), date(2026, 1, 2)),  # New Year's Day
            (date(2026, 3, 19), date(2026, 3, 23)),  # Ramazan Bayramı
            (date(2026, 4, 22), date(2026, 4, 24)),  # National Sovereignty and Children's Day
            (date(2026, 4, 30), date(2026, 5, 4)),  # Labour and Solidarity Day
            (date(2026, 5, 18), date(2026, 5, 20)),  # Atatürk, Youth and Sports Day
            (date(2026, 5, 26), date(2026, 6, 1)),  # Kurban Bayramı
            (date(2026, 7, 14), date(2026, 7, 16)),  # Democracy and National Unity Day
            (date(2026, 10, 28), date(2026, 10, 30)),  # Republic Day
            (date(2026, 12, 31), date(2027, 1, 4)),  # New Year's Day 2027
        ]
        for before, after in cases:
            self.assert_neighbours(before, after)

    def test_recurring_july_15_holiday_applies_to_unconfirmed_years(self) -> None:
        self.assertEqual(next_trading_session(date(2027, 7, 14)), date(2027, 7, 16))


class HalfDaySessionTests(unittest.TestCase):
    def test_confirmed_and_recurring_half_days_are_open_sessions(self) -> None:
        for day in (date(2026, 3, 19), date(2026, 5, 26), date(2026, 10, 28), date(2027, 10, 28)):
            with self.subTest(day=day.isoformat()):
                self.assertTrue(is_trading_session(day))
                self.assertTrue(is_half_day_session(day))

    def test_full_sessions_and_closed_days_are_not_half_days(self) -> None:
        # 2028-10-28 is a Saturday, so the Republic Day eve rule has no session.
        for day in (date(2026, 5, 25), date(2026, 10, 27), date(2026, 10, 29), date(2028, 10, 28)):
            with self.subTest(day=day.isoformat()):
                self.assertFalse(is_half_day_session(day))


class CalendarCoverageWarningTests(unittest.TestCase):
    def test_confirmed_year_has_no_warning(self) -> None:
        self.assertEqual(calendar_coverage_warnings(date(2026, 4, 21), date(2026, 4, 22)), [])

    def test_unconfirmed_year_reports_one_warning(self) -> None:
        warnings = calendar_coverage_warnings(date(2026, 12, 31), date(2027, 1, 4))

        self.assertEqual(len(warnings), 1)
        self.assertIn("2027", warnings[0])
        self.assertNotIn("2026", warnings[0])
        self.assertIn("stock_expert/trading_calendar.py", warnings[0])

    def test_warning_text_is_ascii_for_cp1252_consoles(self) -> None:
        warnings = calendar_coverage_warnings(date(2027, 1, 4))

        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].isascii(), warnings[0])
        self.assertIn("Borsa Istanbul", warnings[0])

    def test_warnings_are_deduplicated_per_year(self) -> None:
        warnings = calendar_coverage_warnings(date(2027, 3, 3), date(2027, 3, 4))

        self.assertEqual(len(warnings), 1)
        self.assertIn("2027", warnings[0])

    def test_warnings_are_sorted_by_year(self) -> None:
        warnings = calendar_coverage_warnings(date(2028, 1, 3), date(2027, 1, 4))

        self.assertEqual(len(warnings), 2)
        self.assertIn("2027", warnings[0])
        self.assertIn("2028", warnings[1])


class ConfirmedCalendarIntegrityTests(unittest.TestCase):
    def test_every_confirmed_date_belongs_to_its_year(self) -> None:
        for year, confirmed in CONFIRMED_VARIABLE_CALENDAR.items():
            with self.subTest(year=year):
                self.assertTrue(confirmed.source)
                self.assertEqual({day.year for day in confirmed.closures | confirmed.half_days}, {year})

    def test_closures_and_half_days_are_disjoint(self) -> None:
        for year, confirmed in CONFIRMED_VARIABLE_CALENDAR.items():
            with self.subTest(year=year):
                self.assertEqual(confirmed.closures & confirmed.half_days, frozenset())

    def test_2026_entry_cites_the_exchange_notice(self) -> None:
        self.assertIn("41625", CONFIRMED_VARIABLE_CALENDAR[2026].source)
        self.assertIn("2025-12-04", CONFIRMED_VARIABLE_CALENDAR[2026].source)

    def test_validation_rejects_a_date_filed_under_the_wrong_year(self) -> None:
        bad = {
            2027: ConfirmedYear(
                source="test",
                closures=frozenset({date(2026, 3, 20)}),
                half_days=frozenset(),
            )
        }
        with self.assertRaisesRegex(ValueError, "another year: 2026-03-20"):
            validate_confirmed_calendar(bad)

    def test_validation_rejects_a_date_that_is_both_closed_and_half_day(self) -> None:
        bad = {
            2026: ConfirmedYear(
                source="test",
                closures=frozenset({date(2026, 3, 19)}),
                half_days=frozenset({date(2026, 3, 19)}),
            )
        }
        with self.assertRaisesRegex(ValueError, "both a closure and a half day: 2026-03-19"):
            validate_confirmed_calendar(bad)

    def test_validation_rejects_weekend_closures_and_half_days(self) -> None:
        saturday = date(2026, 3, 21)
        cases = {
            "closure": ConfirmedYear(source="test", closures=frozenset({saturday}), half_days=frozenset()),
            "half_day": ConfirmedYear(source="test", closures=frozenset(), half_days=frozenset({saturday})),
        }
        for kind, confirmed in cases.items():
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "weekend dates: 2026-03-21"):
                    validate_confirmed_calendar({2026: confirmed})

    def test_validation_rejects_a_closure_that_repeats_a_recurring_holiday(self) -> None:
        bad = {
            2026: ConfirmedYear(
                source="test",
                closures=frozenset({date(2026, 4, 23)}),
                half_days=frozenset(),
            )
        }
        with self.assertRaisesRegex(ValueError, "repeats recurring holiday closures: 2026-04-23"):
            validate_confirmed_calendar(bad)

    def test_validation_rejects_a_half_day_on_a_recurring_holiday(self) -> None:
        bad = {
            2026: ConfirmedYear(
                source="test",
                closures=frozenset(),
                half_days=frozenset({date(2026, 10, 29)}),
            )
        }
        with self.assertRaisesRegex(ValueError, "recurring holiday closures as half days: 2026-10-29"):
            validate_confirmed_calendar(bad)

    def test_validation_accepts_the_shipped_calendar(self) -> None:
        validate_confirmed_calendar(CONFIRMED_VARIABLE_CALENDAR)


if __name__ == "__main__":
    unittest.main()
