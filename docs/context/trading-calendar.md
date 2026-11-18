# BIST Trading Calendar

`stock_expert/trading_calendar.py` is the only owner of BIST equity-market (Pay Piyasası) session routing. Signal dates, target trade dates, review lookups, dated-folder imports, the CLI `routine`, and the Data & Runs preview all derive dates from it. GitHub issue #41.

## Rules

- **Fixed national holidays** are recurring month/day closures: 1 January, 23 April, 1 May, 19 May, 15 July, 30 August, 29 October. A rule that falls on a weekend has no effect.
- **28 October**, the eve of Republic Day, is a recurring half-day session.
- **Variable-date holidays** (Ramazan and Kurban Bayramı, their eves, and any ad-hoc closure) are exact dates per year in `CONFIRMED_VARIABLE_CALENDAR`. They are never modelled as month/day rules because they move every year.
- A half-day session is an open trading session. `is_half_day_session` marks it, and `market_context_for_dates` in `services.py` reports it as `reduced_liquidity` with a `half_holiday_low_liquidity` tag. Half days do not change routing, scoring, or exposure.
- Political-shock dates stay in `services.py` (`POLITICAL_SHOCK_DATES`) because they are a scoring input, not calendar facts.
- `validate_confirmed_calendar` runs at import and rejects a confirmed date filed under the wrong year, marked both closed and half day, falling on a weekend, repeating a recurring closure, or marking a recurring closure as a half day.

## Source

2026 comes from Borsa İstanbul notice 41625 (4 December 2025), appendix EK-3 "Pay Piyasası 2026 Yılı Tatil Tablosu":

| Date | Equity market |
| --- | --- |
| 2026-01-01 | Closed (New Year's Day) |
| 2026-03-19 | Half day (Ramazan Bayramı eve) |
| 2026-03-20 | Closed (Ramazan Bayramı) |
| 2026-04-23 | Closed (National Sovereignty and Children's Day) |
| 2026-05-01 | Closed (Labour and Solidarity Day) |
| 2026-05-19 | Closed (Commemoration of Atatürk, Youth and Sports Day) |
| 2026-05-26 | Half day (Kurban Bayramı eve) |
| 2026-05-27 to 05-29 | Closed (Kurban Bayramı) |
| 2026-07-15 | Closed (Democracy and National Unity Day) |
| 2026-08-30 | Closed, Sunday (Victory Day) |
| 2026-10-28 | Half day (Republic Day eve) |
| 2026-10-29 | Closed (Republic Day) |

2026-05-25 was a normal equity session even though it was an administrative-leave day for public servants.

## Yearly update

Borsa İstanbul publishes the next year's holiday table in an announcement around early December (2026's arrived on 2025-12-04). When it appears:

1. Open the announcement (linked from `https://www.borsaistanbul.com/resmi-tatil-gunleri`, English `https://www.borsaistanbul.com/en/official-holidays`) and use the **Pay Piyasası** table only. The bond, money, swap, precious-metals, and derivatives tables have different hours and closures.
2. Add a `ConfirmedYear` entry for the new year to `CONFIRMED_VARIABLE_CALENDAR`, with every weekday closure that is not already a recurring rule in `closures`, every half day other than 28 October in `half_days`, and the notice number and date in `source`.
3. If the table lists a fixed national holiday the recurring rules do not have, or omits one they do have, stop and decide explicitly. Do not add it silently.
4. Extend `tests/test_trading_calendar.py` with the year's full closure-set test and boundary tests in both directions for each new closure.
5. Record the change in `memory.md` and here.

Until the year is added, `calendar_coverage_warnings` makes the CLI `routine` print a stderr warning and add `calendar_warnings` to its header JSON, and the Data & Runs preview adds the same text to its warnings, whenever the resolved signal date or the target trade date falls in that year. This applies to every year without an entry, including years before 2026 (the database holds no evidence before 2026-04-03). Variable holidays in an unconfirmed year are treated as open full sessions, so the warning has to be resolved before the first one.

## Evidence recorded under the older calendar

Persisted evidence is immutable and is not rebuilt when the calendar changes:

- Review 18 (signal 2026-04-23, review 2026-04-24, 0 picks) was recorded when 2026-04-23 was treated as a session. Under the current calendar a review for 2026-04-24 resolves to signal 2026-04-22, so review 18 is no longer reachable by date lookup. The 2026-04-22 basket was never reviewed.
- No snapshots exist for 2026-10-16 to 2026-10-29, so the 2026-10-29 closure changes no stored basket.
- **Do not run a persisted `review --date 2026-04-24` or a historical `routine --date 2026-04-24`.** Under the current calendar that date resolves to signal 2026-04-22, whose 10-pick basket has no review, so a persisted run would add a 2026-04-22 → 2026-04-24 review and overwrite the existing `weights` row for 2026-04-24 that review 18 wrote. It would also become the newest review in the Evidence Console and shift later candidate-outcome windows. A historical `routine` is worse: it imports today's live CSVs as a 2026-04-24 snapshot and scores the April basket against current prices. Use `review --date 2026-04-24 --dry-run` to inspect it. The same applies to any review date right after a closure added to the calendar later: check `review_runs` for that review date first, and backfill nothing without an explicit decision.
