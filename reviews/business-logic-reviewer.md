# Business-Logic Review

Scope: full strategy path plus recent commits `48dd62a..9ff2846`. All 93 unit tests pass. No P0 finding.

## P1 — BIST calendar omits confirmed full-day closures

**Evidence:** `stock_expert/trading_calendar.py:6-14` lists only five closures. `is_trading_session()` at `:17-18` therefore treats other weekday exchange holidays as sessions. In particular, `next_trading_session(2026-07-14)` returns `2026-07-15`, and `previous_trading_session(2026-07-16)` returns `2026-07-15`; Borsa İstanbul's published 2026 Pay Market calendar says 15 July is closed. The same defect exists for 23 April (`2026-04-22 -> 2026-04-23`). These helpers directly drive target dates and reviews (`stock_expert/services.py:133-138, 672-674, 1012-1014`) and dated-folder routing (`stock_expert/daily_csv.py:232-245`). Existing calendar tests only cover the dates already hard-coded (`tests/test_services.py:44-58`).

**Business impact:** picks can claim a non-trading target date, the next real session can review the wrong signal date, and dated imports can be assigned to a closed date. The 15 July defect is operationally imminent.

**Suggested fix:** source a versioned, authoritative annual BIST calendar (including full closures and explicit half-days), add 2026-04-23 and 2026-07-15 immediately, reject/clearly route routine dates that are not sessions, and add boundary tests in both directions for every closure.

## P1 — Idempotent review storage does not make rerun output immutable

**Evidence:** persisted review rows and pick outcomes are stored atomically (`stock_expert/database.py:721-785`), but `review_output()` always recalculates `recent_rows` from the latest signal/target snapshots before checking whether the review already exists (`stock_expert/services.py:1012-1043`). `get_pick_results()` explicitly resolves both dates to their latest snapshot IDs (`stock_expert/database.py:618-643`). On conflict, only weights are restored from the existing run (`stock_expert/services.py:1127-1133`); performance, reviewed picks, misses, and attribution in the returned payload remain newly recomputed (`:1135-1167`). The reuse test checks only run ID/weights (`tests/test_services.py:475-491`).

**Business impact:** after another same-day import, rerunning the same review can display different returns/misses under the same immutable `review_run_id`; if a newer signal snapshot lacks picks, it can even report `no_prior_picks` despite an existing review. Operator output and persisted audit evidence can disagree.

**Suggested fix:** at the start of non-dry-run review, load an existing review bundle (run, `review_pick_results`, immutable candidate outcomes and stored snapshot metadata) and render from it. Persist target snapshot ID and missed-mover evidence, or explicitly label non-persisted diagnostics as live/recomputed. Add a test that imports newer signal and target snapshots after the first review and asserts byte-stable persisted performance.

## P2 — Adaptive top-3 exposure can activate from incomplete or one-session evidence

**Evidence:** cutoff eligibility requires only `candidate count >= number of sessions` (`stock_expert/services.py:496-517`). Thus one session with ranks 1-3 makes `top_3` eligible, and missing outcomes can leave cutoffs based on unequal session/rank coverage. `adaptive_pick_exposure()` then changes persisted exposure whenever top 3 wins the pooled average and top-5 average is negative (`:406-436`). No minimum session count, completeness check, uncertainty threshold, or effect-size threshold exists. Tests demonstrate three sessions but do not enforce that minimum (`tests/test_services.py:603-642, 861-905`).

**Business impact:** a sparse/cold database or missing next-session ticker prices can cause a strategy-level exposure change from noisy, non-comparable samples.

**Suggested fix:** require a documented minimum number of complete sessions (for example 10), compute each cutoff's equal-weight return per session and compare only common sessions, require rank coverage through 5, and add stability/effect-size criteria plus explicit `insufficient_evidence` output.

## P2 — Miss attribution overwrites the actual exclusion reason

**Evidence:** `_attribution_for_pick()` first assigns `excluded_by_breadth_cap` for ranks between the active and default cutoffs (`stock_expert/services.py:910-914`), then unconditionally overwrites it with `penalized_by_setup_context` whenever setup penalty is nonzero (`:915-916`). Setup penalty may be small and may not be why the candidate missed selection.

**Business impact:** missed-mover diagnostics can falsely claim setup context caused exclusion, obscuring whether breadth/adaptive exposure or rank cutoff was decisive.

**Suggested fix:** emit separate fields such as `selection_status`, `cutoff_reason`, and `context_flags`; derive the decisive reason from rank versus the effective cutoff, and keep setup penalty as supporting attribution only.

## P2 — Companion-file coverage loss is silent

**Evidence:** rows absent from any of `performans`, `teknik`, or `temel` are silently skipped (`stock_expert/daily_csv.py:146-150`), but the import payload reports only successful `rows_read` plus unmapped/malformed counters (`:214-228`).

**Business impact:** a stale or mismatched companion export can shrink breadth, alter exposure, and remove candidates without an operator-visible warning.

**Suggested fix:** count missing joins by source, report input/unmatched counts and universe-retention ratio, and fail or prominently warn when retention falls below a configured threshold.

## Logic confirmed sound

- Signal-date weights are date-bounded (`stock_expert/database.py:596-615`), and adaptive evidence excludes future review dates (`:647-676`).
- Daily snapshot publication and review bundles are transactionally atomic (`stock_expert/database.py:333-356, 721-785`).
- CSV returns are honestly labeled as previous-close-to-latest rather than true open-to-close (`stock_expert/daily_csv.py:158-160, 223`; `stock_expert/services.py:1149-1151`).
- The 4% win threshold is consistently shared through `MIN_DAILY_WIN_RETURN`.
