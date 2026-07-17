# Test Coverage and Quality Review

## Scope and verification

- Reviewed all production modules, all 93 unit tests, and changes from `48dd62a..HEAD`.
- `D:\miniconda3\python.exe -m unittest discover -s tests -v`: **93/93 passed**.
- Independent `trace` run: **2,251/2,390 executable production lines = 94.18% weighted coverage**. Lowest modules: `database.py` 90.44%, `services.py` 92.84%. The documented >=90% line-coverage claim is currently credible.
- P0 findings: **none**.

## P1 — Point-in-time adaptive policy is not tested through the real storage/service boundary

**Evidence:** `stock_expert/services.py:406-437` relies on `get_candidate_outcomes(..., before_review_date=...)`; `stock_expert/database.py:647-676` owns the exclusion query. The service tests replace that query with mocks (`tests/test_services.py:606-630`, `tests/test_services.py:864-898`) and even inject outcomes dated *after* the signal date. Because the mocks ignore `before_review_date`, those tests prove the top-3 calculation but not the anti-leakage contract. The database-only test (`tests/test_review_persistence.py:124-155`) proves filtering in isolation, not that `generate_picks`, `picks_output`, and `review_output` pass the correct boundary.

**Impact:** A future argument regression could silently use later outcomes to change historical/current exposure while all tests remain green, violating the repository's no-future-data rule.

**Suggested fix/tests:** Add a real temporary-SQLite integration test that persists favorable pre-signal and contradictory post-signal candidate outcomes, invokes `generate_picks(..., dry_run=True)` without mocking `get_candidate_outcomes`, and proves post-signal rows cannot change the pick count. Add mock call assertions for `before_review_date=signal_date` in `generate_picks`/`picks_output`, and for the intended inclusive-current-review boundary in `review_output`.

## P1 — Destructive legacy migrations have almost no fixture-based coverage

**Evidence:** `init_db` always invokes migrations (`stock_expert/database.py:160-166`), but trace shows the legacy snapshot migration at `database.py:173-259` and duplicate-review cleanup/column upgrades at `database.py:278-305` are unexecuted. `tests/test_database_prices.py:45-63` starts from the current schema and tests legacy-shaped *upsert input*, not migration from an old database.

**Impact:** A schema upgrade can drop or misassociate stocks, signals, picks, snapshots, review results, or candidate evidence in the user's durable SQLite database without a failing test.

**Suggested fix/tests:** Build minimal pre-migration SQLite fixtures for each supported legacy schema. Run `init_db` twice and assert row-for-row preservation, correct snapshot ownership, enrichment defaults, `selection_bucket`, review metadata, duplicate resolution (including child rows), foreign-key integrity, indexes, and idempotency. Include a forced-failure case proving migration rollback.

## P2 — The >=90% quality gate is documented but not executable or enforced

**Evidence:** `docs/tasks/current.md:27` requires >=90%, but `pyproject.toml` defines no test/coverage command and there is no CI workflow or checked-in trace reporter. Coverage currently passes, but `database.py` has only 0.44 percentage points of per-module headroom.

**Impact:** New untested production code can merge while the documented done criterion silently becomes false; rounded `trace --summary` output can also obscure a near-threshold regression.

**Suggested fix/tests:** Add a standard-library coverage script that runs discovery under `trace`, counts exact executable/hit lines for `stock_expert/*.py`, and exits nonzero if weighted or per-module coverage falls below the agreed threshold. Test the reporter itself and run it in the normal verification workflow.

## P2 — Routine tests verify labels and mocked routing, not a real end-to-end persisted workflow

**Evidence:** `tests/test_cli.py:158-230` mocks import, summaries, picks, review, and diagnostics. Persistence tests cover lower-level bundles, but no test invokes a routine against four CSV fixtures and a temporary database, then verifies snapshot, picks, review, weights, candidate outcomes, idempotent rerun, and dry-run boundaries together.

**Impact:** Cross-layer ordering/date/snapshot regressions can pass unit tests even though the operator's primary command fails or writes inconsistent state.

**Suggested fix/tests:** Add one compact CLI/service integration fixture with mapped equities and two trading dates. Exercise `routine` and `midday-routine`; assert output sections plus exact database effects, rerun idempotency, latest-snapshot selection, holiday routing, and that midday review adds no review/weight/outcome rows.

## Areas adequately covered

- Atomic daily snapshot rollback and review-bundle rollback/idempotency.
- Latest-snapshot reads, historical weight cutoff, and candidate date filtering in isolation.
- Ranking/enrichment bounds, breadth/adaptive exposure behavior, attribution, and 4% win threshold.
- Yahoo normalization/parsing/retry/export/import paths and CLI argument routing.
- Shared holiday routing and documentation-stop hook behavior.
