# Rolling Candidate Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve portfolio evidence and risk control by recording candidate outcomes, reporting rolling miss patterns, and reducing exposure in weak breadth.

**Architecture:** Extend SQLite with idempotent candidate outcome rows keyed by signal date, review date, and ticker. Review recomputes the signal-date ranking, records next-session outcomes for the top candidates, and summarizes rolling rank-band, setup-penalty, breakout, and strategy results. Pick generation applies a simple breadth-based pick-count cap without changing ranking.

**Tech Stack:** Python 3.11, SQLite, standard-library `unittest`

---

### Task 1: Behavior Tests

**Files:**
- Modify: `tests/test_services.py`

- [ ] Add failing tests for weak-breadth exposure reduction.
- [ ] Add failing tests for candidate outcome persistence and rolling diagnostic output.
- [ ] Run focused tests and confirm failures are caused by missing behavior.

### Task 2: Candidate Outcome Persistence

**Files:**
- Modify: `stock_expert/database.py`
- Modify: `stock_expert/services.py`

- [ ] Add the candidate outcome schema and idempotent replace/read functions.
- [ ] Record top-ranked candidate outcomes during persisted review.
- [ ] Run focused tests until green.

### Task 3: Exposure And Rolling Evaluation

**Files:**
- Modify: `stock_expert/config.py`
- Modify: `stock_expert/services.py`

- [ ] Add breadth-based pick-count caps.
- [ ] Add rolling rank-band, miss-pattern, cumulative strategy, and review-weight diagnostics.
- [ ] Run focused tests until green.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/features/picks.md`
- Modify: `docs/features/review.md`
- Modify: `docs/context/decisions.md`
- Modify: `memory.md`

- [ ] Document behavior and durable workflow decisions.
- [ ] Run the full test suite.
- [ ] Run current-data dry-run checks and inspect output.
