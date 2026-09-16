# Data Quality & Snapshot History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist daily-CSV snapshot provenance and validation metrics atomically, then expose lineage, coverage, mapping failures, and prior-snapshot comparison through a read-only Snapshots view.

**Architecture:** Quality columns and `provenance_captured` live on `snapshot_runs`. Unmapped company names live in `snapshot_mapping_failures`, written in the same `persist_daily_snapshot` transaction. Read-only `/api/snapshots/history` and `/api/snapshots/{id}` never call ranking. The Evidence Console adds `ViewKey` `snapshots`, reachable without latest picks.

**Tech Stack:** Python 3.11+ stdlib, SQLite, `unittest`, React/Vite Evidence Console, Node test runner. No new dependencies.

## Global Constraints

- Requirement ticket remains [GitHub issue #11](https://github.com/beagle1903/stock-expert/issues/11).
- Publication stays one SQLite transaction; failed bundles create no `snapshot_runs` row.
- Existing snapshots and `create_snapshot_run` rows stay `provenanceStatus: "not_captured"`.
- Do not backfill, persist failed attempts, change scoring/selection, or invent trading UI.
- Data & Runs remains the only mutating web surface.
- `/api/picks/latest` still selects the newest snapshot that owns picks.
- Python: `D:\miniconda3\python.exe`. Skip `git commit` unless the user asked.
- After persistence work: `se-strategy-review`. After Evidence Console work: `se-ui-review`. Do not nest subagents.
- Parent owns issues, branches, and commits. `se-implement` does one scoped change.

---

### Task 1: Persist provenance in the snapshot transaction

**Files:**
- Modify: `stock_expert/database.py` (`SCHEMA`, `init_db`, `persist_daily_snapshot`)
- Modify: `stock_expert/daily_csv.py` (`import_daily_csv_command`)
- Test: `tests/test_daily_csv.py`

**Interfaces:**
- Consumes: existing `persist_daily_snapshot(settings, snapshot_date, source_label, source_dir, market_rows, price_rows) -> int`
- Produces:
  - `MAX_SNAPSHOT_MAPPING_FAILURES = 50`
  - `persist_daily_snapshot(..., quality: SnapshotQuality | None = None) -> int`
  - `SnapshotQuality` TypedDict with `rows_read`, `distinct_tickers`, `mapped_count`, `skipped_non_equity_count`, `skipped_unmapped_count`, `skipped_malformed_count`, `ticker_coverage`, `decimal_separator`, `price_basis`, `source_files`, `unmapped_names: list[str]`

- [x] **Step 1: Write failing persistence tests** in `tests/test_daily_csv.py`

```python
def test_daily_import_persists_provenance_metrics(self) -> None:
    payload = json.loads(import_daily_csv_command(self.settings, "2026-04-21"))
    row = self._snapshot_row(payload["snapshot_id"])
    self.assertEqual(row["provenance_captured"], 1)
    self.assertEqual(row["skipped_unmapped_count"], payload["skipped_unmapped_count"])
    self.assertAlmostEqual(row["ticker_coverage"], payload["ticker_coverage"])

def test_legacy_snapshot_rows_are_not_captured(self) -> None:
    snapshot_id = create_snapshot_run(self.settings, date(2026, 4, 21), "test", "data")
    row = self._snapshot_row(snapshot_id)
    self.assertEqual(row["provenance_captured"], 0)
    self.assertIsNone(row["ticker_coverage"])

def test_failed_snapshot_write_rolls_back_quality_rows(self) -> None:
    # extend existing rollback test: no new snapshot_runs or mapping_failures
```

- [x] **Step 2: Run** `D:\miniconda3\python.exe -m unittest tests.test_daily_csv -v`
  Expected: FAIL on missing columns / quality argument.

- [x] **Step 3: Implement schema + persist**
  - `ALTER TABLE` helpers `_ensure_snapshot_provenance` using `_has_column`.
  - Create `snapshot_mapping_failures` if missing.
  - When `quality` is provided, UPDATE captured columns, set `provenance_captured=1`, INSERT up to 50 unmapped names.
  - `import_daily_csv_command` collects unmapped names during the skip loop and passes `quality` after the coverage gate.

- [x] **Step 4: Re-run** `tests.test_daily_csv` plus `tests.test_database_prices`. Expected: PASS.
  Coverage-gate test must still publish nothing.

---

### Task 2: Read-only snapshot history and comparison API

**Files:**
- Modify: `stock_expert/web_api.py` (`do_GET`, new loaders)
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `snapshot_runs` + `snapshot_mapping_failures`
- Produces:
  - `load_snapshot_history(settings) -> list[dict]`
  - `load_snapshot_detail(settings, snapshot_id: int) -> dict | None`
  - Routes: `GET /api/snapshots/history`, `GET /api/snapshots/{id}`

History item:

```python
{
    "id": 12,
    "snapshotDate": "2026-04-21",
    "importedAt": "...",
    "source": "daily_csv",
    "sourceDir": "data",
    "provenanceStatus": "captured",  # or "not_captured"
    "publicationResult": "published",
    "rowsRead": 640,  # null if not_captured
    "distinctTickers": 640,
    "skippedUnmappedCount": 3,
    "skippedMalformedCount": 0,
    "tickerCoverage": 0.91,
    "unmappedTruncated": False,
}
```

Detail adds `mappingFailures: list[str]`, `decimalSeparator`, `priceBasis`, `sourceFiles`, and:

```python
"comparison": {
    "status": "available",  # unavailable | not_captured | available
    "priorSnapshotId": 11,
    "coverageRegression": True,
    "mappingFailureIncrease": False,
    "deltas": {
        "tickerCoverage": -0.04,
        "rowsRead": -12,
        "distinctTickers": -12,
        "skippedUnmappedCount": 2,
        "skippedMalformedCount": 0,
    },
}
```

Prior snapshot is `WHERE id < :id ORDER BY id DESC LIMIT 1`. Deltas only when both rows are captured.

- [x] **Step 1: Write failing API tests** for captured detail, legacy `not_captured`, no-prior `unavailable`, pick-less history inclusion, 404 for unknown id.
- [x] **Step 2: Run** `D:\miniconda3\python.exe -m unittest tests.test_web_api -v` — FAIL on missing routes.
- [x] **Step 3: Implement loaders and `do_GET` branches.** Do not call `rank_candidates`.
- [x] **Step 4: Re-run web API tests.** Expected: PASS.

Then parent launches `se-strategy-review` on persistence + API. Report requested vs actual model.

---

### Task 3: Read-only Snapshots view

**Files:**
- Modify: `frontend/src/domain/dashboard.ts` (`ViewKey`)
- Create: `frontend/src/domain/snapshotHistory.ts`
- Create: `frontend/src/data/snapshotHistoryRepository.ts`
- Create: `frontend/src/data/snapshotHistoryViewModel.mjs` (+ `.d.mts`)
- Modify: `frontend/src/App.tsx`, `frontend/src/data/strategyEvidenceViewModel.mjs`
- Test: `frontend/tests/snapshot-history.test.mjs`
- Modify: `frontend/tests/strategy-evidence.test.mjs` (`appContentMode("snapshots", false)` must not be `dashboard_unavailable`)

**Interfaces:**
- Consumes: Task 2 JSON
- Produces: `appContentMode` returns `snapshot_history` when `activeView === "snapshots"`
- Nav label: `Snapshots`. Query: `?view=snapshots`.

View model copy:
- captured: show counts, coverage %, mapping names
- not_captured: "Provenance was not captured for this snapshot."
- comparison unavailable: "No prior published snapshot."
- coverageRegression: "Coverage is lower than snapshot #N."
- mappingFailureIncrease: "Unmapped rows increased versus snapshot #N."

- [x] **Step 1: Write failing frontend tests** for those four states and independent content mode.
- [x] **Step 2: Run** `npm test --prefix frontend` — FAIL.
- [x] **Step 3: Implement types, repository, view, nav, lazy load like Strategy Lab.** No mutate controls.
- [x] **Step 4: Re-run frontend tests.** Expected: PASS.

Then parent launches `se-ui-review`. Report requested vs actual model.

---

### Task 4: Docs and verification

**Files:**
- Modify: `docs/features/dashboard.md`, `docs/context/architecture.md`, `docs/context/decisions.md`, `docs/tasks/current.md`, `docs/tasks/backlog.md`, `memory.md`, `docs/tasks/data-quality-snapshot-history.md`

- [x] **Step 1: Update docs** to match shipped behavior. Issue #11 stays open until the user asks to close it.
- [x] **Step 2: Run**
  - `D:\miniconda3\python.exe -m unittest discover -s tests -v` — 174 OK
  - frontend tests (25 pass) and production build
  - trace coverage not re-measured this pass
- [x] **Step 3: Browser-verify** Snapshots on desktop and ~390px: live rows are `not_captured` until the next import; #1 has no prior; #149 compares with #148. Data & Runs still launches; reviews unchanged.

## Spec Coverage

| Spec requirement | Task |
| --- | --- |
| Atomic persist of provenance + metrics | 1 |
| Failed bundles unpublished | 1 |
| Legacy `not_captured` | 1, 2, 3 |
| History, lineage, mapping failures | 2, 3 |
| Prior-snapshot comparison / regressions | 2, 3 |
| Read-only dashboard view | 3 |
| Tests + docs | 1–4 |
| No trading UI / no strategy change | Global |
