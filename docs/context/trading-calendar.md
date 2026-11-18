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
- **A persisted `review --date 2026-04-24` or historical `routine --date 2026-04-24` is refused.** Under the current calendar that date resolves to signal 2026-04-22, whose 10-pick basket has no review. A persisted run would add a 2026-04-22 → 2026-04-24 review, overwrite the 2026-04-24 `weights` row that review 18 wrote, become the newest review in the Evidence Console, and shift later candidate-outcome windows. A historical `routine` would also import today's live CSVs as a 2026-04-24 snapshot. `review --date 2026-04-24 --dry-run` still works for inspection.

## Review evidence guard

A persisted review for review date R resolves its signal date S as `previous_trading_session(R)`. Before writing anything, `review` and `routine` refuse (exit 1, a `review:` or `routine:` message on stderr) when `review_runs` already holds either:

- a review for R from a different signal date (R was reviewed under an older calendar, as with review 18), or
- a review of S's basket against a different review date (the basket was already evaluated, as with review 136 for 2026-11-06, so `review --date 2026-11-09` is refused).

A persisted `review` for a review date that is not an open trading session (a weekend or closure) is refused too. Such a run would otherwise record the signal basket's pilot session with nothing evaluated, so the real next-session review would skip that basket's pilot outcome. `routine` is not affected because it resolves a non-session date to the previous session first.

When the exact (S, R) review already exists and R is a trading session, the run is the normal idempotent rerun and is not refused, even if a conflicting row also exists. The non-session check comes first, so a rerun of review 136's own Saturday key (`review --date 2026-11-07`) is refused as well. `routine` runs the check before importing, so a refused run imports no snapshot. The Data & Runs preview lists the conflict as a blocking issue, and the Run control stays disabled. `--dry-run` is never blocked. The guard has no override flag. Resolving a conflict, for example re-reviewing a basket that review 136 measured against the wrong day, needs an explicit decision and a deliberate data change.

**If today's routine is refused**, report the message and stop. The next session's routine passes normally once its own key is clear. If the operator decides today's basket must still be published without its review, the CLI path is `python.exe -m stock_expert import-daily-csv --date D`, then a persisted `python.exe -m stock_expert picks --date D`. Data & Runs has no equivalent.
