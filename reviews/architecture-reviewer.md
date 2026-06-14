# Architecture Review

Scope: entire repository plus `git diff HEAD~5..HEAD`, focused on module boundaries, persistence contracts, coupling, idempotency, data flow, migrations, maintainability, and documented decisions.

## Findings

### P1 - A failed CSV import can publish a partial snapshot as the latest snapshot

**Evidence:** `stock_expert/daily_csv.py:196-204` creates and commits `snapshot_runs` first, then writes `market_snapshots` and `stocks` through two more independently committed database calls. `stock_expert/database.py:264-290` treats the highest run id as the latest snapshot without any completion state.

**Impact:** If either row write fails, the committed run remains the newest snapshot for that date. All date-based reads can then select an empty or half-populated snapshot, causing missing picks, mismatched price/snapshot context, or replacement of valid persisted picks with an empty set.

**Reasoning:** A snapshot is the project's main operating input and must be an atomic publication unit. The current API exposes the run before its dependent rows are durable.

**Suggested fix:** Add one database operation that inserts `snapshot_runs`, `market_snapshots`, and `stocks` on the same connection and transaction. Alternatively add a `status` column (`loading`/`complete`) and make all latest-snapshot queries select only `complete`, setting it only after both row sets succeed. Add fault-injection tests for failure before each write.

### P1 - Historical ranking and review-weight calculations use future state

**Evidence:** `_ranked_candidate_rows()` requests the globally latest weights regardless of its `as_of` argument (`stock_expert/services.py:252-264`; `stock_expert/database.py:455-464`). Historical review recomputation calls this path for `signal_date` (`stock_expert/services.py:894-907`). Rolling review weights also load the latest weight and the latest 19 review runs without filtering to rows before the requested review date (`stock_expert/services.py:947-955`; `stock_expert/database.py:584-597`).

**Impact:** Re-running an older review after later sessions exist can rank candidates with later weights and calculate its adjustment from future review outcomes. This makes historical diagnostics non-reproducible and violates the documented decisions "No future data leakage" and "Only use data available at decision time" (`docs/context/decisions.md:6-7`).

**Reasoning:** Date-parameterized workflows need date-bounded dependencies. A global "latest" query is only valid for today's forward run, not historical recomputation.

**Suggested fix:** Replace `get_latest_weights()` in date-scoped flows with `get_weights_as_of(date)` using `WHERE date <= ?`. Add `before_review_date` to `get_recent_review_runs()` and filter `review_date < ?`. Persist or pass the exact weight version used by the signal snapshot. Add tests that insert later weights/reviews and prove an older review output is unchanged.

### P1 - Idempotent review reruns overwrite historical candidate evidence with current logic

**Evidence:** Even when an existing review is found and reused, `review_output()` always recomputes bucketed/ranked candidates and calls `replace_candidate_outcomes()` (`stock_expert/services.py:965-991`). That function deletes the prior rows and inserts replacements (`stock_expert/database.py:503-545`). The table key contains only dates and ticker, with no `review_run_id`, `signal_snapshot_id`, or strategy/version identity (`stock_expert/database.py:114-131`).

**Impact:** A rerun after a newer same-day snapshot, weight change, or ranking-code change silently rewrites the rolling evidence used to justify strategy cutoffs. The persisted review result stays fixed while its supporting candidate population changes, so the review is only partially idempotent.

**Reasoning:** Analytical evidence intended for longitudinal decisions must be anchored to the immutable decision context that produced it.

**Suggested fix:** Persist candidate outcomes only when creating the review run, in the same transaction. Add `review_run_id`, `signal_snapshot_id`, weight/version fields, and a strategy version/hash. On ordinary reruns, read the existing rows. If backfills are needed, write a new version rather than replacing evidence in place. Extend `tests/test_services.py:410-458` to assert candidate rows are unchanged on rerun.

### P1 - Review persistence is not an atomic or database-enforced idempotent operation

**Evidence:** `review_output()` writes weights, the review run/results, and candidate outcomes through three separate database transactions (`stock_expert/services.py:965-991`). `review_runs` has no unique constraint on `(as_of_date, review_date)` (`stock_expert/database.py:89-100`), so idempotency relies on a non-atomic check followed by insert.

**Impact:** A failure after `insert_weights()` can change future rankings without recording the review that caused it. A failure before candidate outcomes leaves an incomplete review bundle. Concurrent invocations can both pass `get_review_run()` and create duplicate review runs.

**Reasoning:** The review run, pick results, resulting weights, and candidate outcomes form one domain transaction.

**Suggested fix:** Introduce `persist_review_bundle()` that uses one connection and transaction, add `UNIQUE(as_of_date, review_date)`, and use `INSERT ... ON CONFLICT` or handle the uniqueness error by loading the existing run. Include rollback and concurrent-idempotency tests.

### P2 - Persistence relationships are mostly unenforced and under-documented

**Evidence:** `stocks`, `signals`, `picks`, and `market_snapshots` carry `snapshot_id` but declare no foreign key to `snapshot_runs` (`stock_expert/database.py:14-87`). The only declared foreign key is `review_pick_results.review_run_id`, while connections do not enable SQLite foreign-key enforcement (`stock_expert/database.py:102-144`). `candidate_outcomes` is linked only by duplicated date strings. The architecture document still lists only six tables and omits `review_runs`, `review_pick_results`, and `candidate_outcomes` (`docs/context/architecture.md:14-18`).

**Impact:** Cleanup or manual repair can leave orphan rows, and maintainers cannot infer lifecycle/ownership rules from either schema enforcement or architecture documentation.

**Reasoning:** Snapshot and review ownership are core persistence boundaries, not optional metadata.

**Suggested fix:** Enable `PRAGMA foreign_keys = ON`, migrate snapshot-owned tables to reference `snapshot_runs(id)`, link candidate outcomes to `review_runs`, and define deliberate cascade/restrict behavior. Update the architecture persistence inventory and lifecycle description.

### P2 - Detached or unrecognized git state falls back to the main database

**Evidence:** `_default_db_path()` maps an empty branch name to `data/stock_expert.db` (`stock_expert/config.py:49-64`). `git branch --show-current` returns an empty string in detached HEAD state, and command failure is also converted to an empty string. This is the same path reserved for `main`, despite the documented isolation goal (`memory.md:46`; `docs/context/decisions.md:31`).

**Impact:** Running commands from a detached worktree, exported source tree, or environment where git lookup fails can silently read and mutate the primary database. This defeats the branch-isolation safeguard precisely when repository identity is uncertain.

**Reasoning:** Unknown execution context should fail closed or choose an isolated database, not assume stable `main`.

**Suggested fix:** Resolve `main` only when the branch name is explicitly `main`. For empty/error states, use a deterministic isolated filename such as `stock_expert_detached_<short-sha>.db`, require `STOCK_EXPERT_DB_PATH`, or abort mutating commands with a clear message. Add unit tests for main, feature branch, detached HEAD, git failure, and environment override.

### P2 - Trading-session policy is duplicated across modules and already disagrees

**Evidence:** The canonical service helpers skip weekends and `USER_CONFIRMED_MARKET_HOLIDAYS` (`stock_expert/services.py:44-52`, `stock_expert/services.py:117-128`). The CSV-folder adapter defines a separate `_previous_weekday()` that skips only weekends and uses it to assign the imported snapshot date (`stock_expert/daily_csv.py:225-242`). For a folder labeled `20260601`, the adapter derives `2026-05-29`, while the service policy correctly derives `2026-05-26` because May 27-29 are closed.

**Impact:** The legacy/manual folder command can persist a snapshot under a closed exchange date. Subsequent picks and reviews then disagree about which session the data represents, undermining snapshot ownership and the documented exact-holiday decision.

**Reasoning:** Trading-session calculation is a domain policy and should have one owner. Keeping a private approximation in an input adapter guarantees drift whenever the holiday calendar changes.

**Suggested fix:** Move trading-session helpers and the exact-date calendar into a dependency-neutral module such as `stock_expert/trading_calendar.py`, and make both services and import adapters use it. Add folder-import tests for weekends and the May 27-29, 2026 closure window.

## Residual Risks And Test Gaps

- No test simulates import failure between run creation and dependent row writes.
- No test proves historical reviews exclude later weights, snapshots, or review sessions.
- No test verifies candidate outcomes remain immutable on an idempotent rerun.
- No test covers concurrent review execution or transaction rollback.
- Migration coverage does not validate review/candidate constraints or foreign-key behavior.
- No config test covers detached HEAD or git-command failure database selection.
- No folder-import test verifies that snapshot-date derivation shares the holiday-aware trading calendar.

## Verification

- `D:\miniconda3\python.exe -m unittest discover -s tests -v`
- Result: 56 tests passed.

## Summary

No P0 findings. Four P1 findings affect snapshot publication, temporal correctness, evidence immutability, and review transaction integrity. Three P2 findings cover unenforced persistence ownership, architecture-document drift, unsafe fallback database selection, and duplicated trading-calendar policy.

Paths changed:

- `reviews/architecture-reviewer.md`
