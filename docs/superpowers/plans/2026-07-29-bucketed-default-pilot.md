# Bucketed-Default Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bucketed selection the controlled persisted default for up to ten complete paired sessions, with complete score-ranked control evidence, fixed pilot weights, and automatic rollback or promotion.

**Architecture:** A pure `pilot.py` policy evaluates paired session summaries without I/O. SQLite stores one pilot state, both signal-time baskets, and realized arm/session outcomes. Existing services create both breadth-matched arms from one cached ranking, persist the selected arm through `picks`, freeze rolling weight changes while active, and expose the state in CLI JSON.

**Tech Stack:** Python 3.11+, standard-library `dataclasses`, `sqlite3`, `unittest`, existing Stock Expert service and CLI layers.

## Global Constraints

- Pilot name is exactly `bucketed-default-v1`.
- Both arms use the same existing breadth-adjusted pick count.
- Candidate scoring and momentum/volume values do not change.
- Active pilot weights remain fixed at their start values.
- Only fully evaluated paired sessions advance the counter.
- Roll back at a compounded bucketed-minus-score edge of `-0.03` or worse.
- Promote after 10 sessions only with at least 6 bucketed session wins and at least `0.03` compounded edge.
- Do not add dependencies or frontend controls.
- Keep existing review idempotency and transaction boundaries.

---

### Task 1: Pure Pilot Decision Policy

**Files:**
- Create: `stock_expert/pilot.py`
- Create: `tests/test_pilot.py`

**Interfaces:**
- Consumes: session rows containing `strategy`, `avg_return`, and `is_complete`.
- Produces: `evaluate_pilot_sessions(rows) -> PilotEvaluation` and `operational_strategy(status: str | None) -> str`.

- [ ] **Step 1: Write failing policy tests**

```python
def test_rolls_back_at_negative_three_point_compounded_edge(self):
    rows = paired_rows([0.00], [-0.03])
    result = evaluate_pilot_sessions(rows)
    self.assertEqual(result.status, "rolled_back")

def test_promotes_only_after_ten_sessions_with_both_thresholds(self):
    rows = paired_rows([0.00] * 10, [0.004] * 10)
    result = evaluate_pilot_sessions(rows)
    self.assertEqual(result.status, "promoted")
    self.assertEqual(result.bucketed_session_wins, 10)

def test_fails_after_ten_sessions_without_required_edge(self):
    rows = paired_rows([0.00] * 10, [0.001] * 10)
    self.assertEqual(evaluate_pilot_sessions(rows).status, "failed")
```

- [ ] **Step 2: Run the focused tests and confirm the missing module failure**

Run: `D:\miniconda3\python.exe -m unittest tests.test_pilot -v`

Expected: import failure for `stock_expert.pilot`.

- [ ] **Step 3: Implement the minimal pure policy**

```python
@dataclass(frozen=True)
class PilotEvaluation:
    status: str
    completed_sessions: int
    bucketed_session_wins: int
    score_compounded_return: float
    bucketed_compounded_return: float
    compounded_edge: float
    decision_reason: str

def operational_strategy(status: str | None) -> str:
    return "score_ranked" if status in {"rolled_back", "failed"} else "bucketed"
```

Group only complete score/bucketed pairs by signal snapshot, compound each arm
with `math.prod(1.0 + value) - 1.0`, apply rollback before the ten-session
decision, and round stored return metrics to six decimals.

- [ ] **Step 4: Run focused tests**

Run: `D:\miniconda3\python.exe -m unittest tests.test_pilot -v`

Expected: all pilot policy tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- stock_expert/pilot.py tests/test_pilot.py
git commit -m "feat: add bucketed pilot policy"
```

### Task 2: Pilot Persistence and Atomic Review Evidence

**Files:**
- Modify: `stock_expert/database.py`
- Modify: `tests/test_review_persistence.py`

**Interfaces:**
- Consumes: `PilotEvaluation` from Task 1 and basket dictionaries from services.
- Produces:
  - `ensure_strategy_pilot(settings, signal_date, weights) -> sqlite3.Row`
  - `get_strategy_pilot_state(settings) -> sqlite3.Row | None`
  - `replace_strategy_pilot_baskets(settings, snapshot_id, signal_date, target_trade_date, baskets) -> None`
  - `get_strategy_pilot_baskets(settings, snapshot_id) -> list[sqlite3.Row]`
  - optional `pilot_target_prices` argument on `persist_review_bundle`.

- [ ] **Step 1: Write failing schema and round-trip tests**

Add tests that initialize a temporary database, ensure one active state row,
replace both baskets for one snapshot, and assert all rows and fixed weights
round-trip. Add a review-bundle test with complete target prices and assert:

```python
self.assertEqual(state["completed_sessions"], 1)
self.assertEqual(state["bucketed_session_wins"], 1)
self.assertEqual(session_rows[0]["is_complete"], 1)
self.assertEqual(outcome_rows["BBB"]["return_pct"], 0.05)
```

Also patch the pilot result insertion helper to raise and assert that the
existing review, weights, candidate outcomes, pilot session rows, and pilot
pick outcomes all remain uncommitted.

- [ ] **Step 2: Run persistence tests and confirm missing-table/function failures**

Run: `D:\miniconda3\python.exe -m unittest tests.test_review_persistence -v`

Expected: failures identify missing pilot schema and database interfaces.

- [ ] **Step 3: Add schema and migration-safe database functions**

Create `strategy_pilot_state`, `strategy_pilot_picks`, and
`strategy_pilot_sessions` with primary keys described in the design. Insert
state with `INSERT OR IGNORE`, replace baskets only for the exact pilot and
snapshot, and expose read helpers ordered by strategy and selection rank.

- [ ] **Step 4: Extend the review transaction**

Add `pilot_target_prices: dict[str, object] | None = None` to
`persist_review_bundle`. After existing review evidence is inserted, update
every stored pilot basket row for `signal_snapshot_id`, insert both arm
summaries, evaluate complete paired sessions, and update the non-terminal state
in the same connection. Keep the existing early return unchanged on an
idempotent rerun.

- [ ] **Step 5: Run persistence tests**

Run: `D:\miniconda3\python.exe -m unittest tests.test_review_persistence -v`

Expected: all persistence tests pass.

- [ ] **Step 6: Commit**

```powershell
git add -- stock_expert/database.py tests/test_review_persistence.py
git commit -m "feat: persist paired pilot evidence"
```

### Task 3: Strategy Selection, Breadth Matching, and Weight Freeze

**Files:**
- Modify: `stock_expert/services.py`
- Modify: `tests/test_services.py`

**Interfaces:**
- Consumes: Task 2 state and basket persistence functions.
- Produces:
  - `_strategy_baskets(ranked, snapshots, pick_count) -> dict[str, list[PickRow]]`
  - `ensure_bucketed_default_pilot(settings, signal_date) -> dict[str, object]`
  - `strategy_pilot_payload(settings) -> dict[str, object]`
  - `generate_picks` that persists the operational arm and both evidence arms.

- [ ] **Step 1: Write failing selection tests**

Add tests proving:

```python
self.assertEqual([pick.ticker for pick in actual], ["BUCKET"])
self.assertEqual(saved_baskets["score_ranked"][0].ticker, "SCORE")
self.assertEqual(saved_baskets["bucketed"][0].ticker, "BUCKET")
```

Cover an active state, a rolled-back state, equal breadth caps for both arms,
and no basket writes during `dry_run=True`.

- [ ] **Step 2: Run focused service tests and confirm expected failures**

Run: `D:\miniconda3\python.exe -m unittest tests.test_services.ServicesTests.test_active_pilot_persists_bucketed_default_and_both_baskets tests.test_services.ServicesTests.test_rolled_back_pilot_persists_score_ranked_default -v`

Expected: failures show score-ranked is still unconditional and pilot baskets
are not persisted.

- [ ] **Step 3: Implement strategy basket selection**

Build score-ranked picks with `selection_bucket="score_ranked"` and bucketed
picks through `_select_bucketed_picks`, both limited by the same
`final_pick_count`. Choose with `operational_strategy(state["status"])`.
Persist actual picks through the existing `replace_picks_for_date`, then persist
both evidence baskets for the same snapshot and target trading date.

- [ ] **Step 4: Write and verify failing weight-isolation tests**

Add one active-pilot review test asserting the resulting momentum and volume
weights equal the pilot state values even when rolling evidence would change
them. Run that single test and confirm it fails because rolling weights still
move.

- [ ] **Step 5: Freeze weights and connect review outcomes**

While state is active, use its fixed weights as `next_weights`; otherwise retain
the existing rolling review behavior. Pass current review prices to
`persist_review_bundle` so both stored arms are evaluated. Add the selected
strategy and compact state fields to pick and review JSON.

- [ ] **Step 6: Run service tests**

Run: `D:\miniconda3\python.exe -m unittest tests.test_services -v`

Expected: all service tests pass.

- [ ] **Step 7: Commit**

```powershell
git add -- stock_expert/services.py tests/test_services.py
git commit -m "feat: run bucketed default pilot"
```

### Task 4: Routine Ordering and Operator Output

**Files:**
- Modify: `stock_expert/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ensure_bucketed_default_pilot`, `review_output`, and
  `picks_output`.
- Produces: full routine mutation order `initialize -> review -> picks`, with
  existing printed section order retained.

- [ ] **Step 1: Write the failing routine-order test**

Use side effects to append call names and assert:

```python
self.assertLess(calls.index("review"), calls.index("picks"))
self.assertLess(output.index("Pick List:"), output.index("Review:"))
```

Also assert pilot initialization is absent from `midday-routine`.

- [ ] **Step 2: Run CLI tests and confirm the order failure**

Run: `D:\miniconda3\python.exe -m unittest tests.test_cli.CliTests.test_routine_reviews_before_persisting_current_picks -v`

Expected: review currently occurs after picks.

- [ ] **Step 3: Implement mutation ordering without changing display ordering**

For `routine`, initialize the state, compute the market summary, capture the
review string, then capture the pick string. Print the stored strings in the
existing market, picks, review, comparison, and downside order. Preserve the
existing `midday-routine` path and dry-run review.

- [ ] **Step 4: Run CLI tests**

Run: `D:\miniconda3\python.exe -m unittest tests.test_cli -v`

Expected: all CLI tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- stock_expert/cli.py tests/test_cli.py
git commit -m "feat: apply pilot rollback before next picks"
```

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `docs/features/picks.md`
- Modify: `docs/features/review.md`
- Modify: `docs/context/architecture.md`
- Modify: `docs/context/decisions.md`
- Modify: `docs/tasks/current.md`
- Modify: `memory.md`

**Interfaces:**
- Consumes: implemented behavior from Tasks 1-4.
- Produces: durable operator and architecture documentation.

- [ ] **Step 1: Update feature and architecture documentation**

Document the pilot thresholds, fixed-weight period, complete paired evidence,
terminal-state behavior, table ownership, and review-before-picks mutation
order. Mark the controlled pilot implementation in the current task.

- [ ] **Step 2: Run focused and full verification**

```powershell
D:\miniconda3\python.exe -m unittest tests.test_pilot tests.test_review_persistence tests.test_services tests.test_cli -v
D:\miniconda3\python.exe -m unittest discover -s tests -v
git diff --check
```

Expected: zero test failures and no whitespace errors.

- [ ] **Step 3: Verify coverage remains at least 90 percent**

Run the repository's documented standard-library trace coverage command from
`openwiki/testing.md`, then calculate weighted production-line coverage.

Expected: at least 90 percent.

- [ ] **Step 4: Run a branch-database smoke check**

Resolve `get_settings().db_path`, initialize it, read the pilot state, run
`picks --dry-run` for an available snapshot date, and verify the production
`data/stock_expert.db` was not modified by branch testing.

- [ ] **Step 5: Inspect final state and commit documentation**

```powershell
git status --short
git diff --stat main...HEAD
git log --oneline main..HEAD
git add -- docs/features/picks.md docs/features/review.md docs/context/architecture.md docs/context/decisions.md docs/tasks/current.md memory.md
git commit -m "docs: document bucketed strategy pilot"
```

Expected: only planned files are changed before the documentation commit, and
the branch contains focused pilot commits.
