# Fade-Then-Rechase Penalty

GitHub issue: [#21](https://github.com/beagle1903/stock-expert/issues/21)

## Behavior

- Prior two completed sessions (close-to-close, excluding the signal date) drive a score penalty when an older session was ~+10% and yesterday was not.
- Immediate next-day continuation after ~+10% is unchanged.
- Weak-breadth extra penalty applies when the signal-date pick cap is already below 5.
- New reviews tag UNLU-class misses as `setup_penalized_limit_up` (non-actionable) and TKFEN-class ranks as `near_cutoff`.
- Existing review rows are not rewritten.

## Verification

`D:\miniconda3\python.exe -m unittest tests.test_services.EnrichmentSignalTests tests.test_services.ReviewOutputTests -v`
