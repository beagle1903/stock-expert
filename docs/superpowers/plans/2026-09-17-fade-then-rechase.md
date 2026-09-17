# Fade-Then-Rechase Implementation Plan

> **For agentic workers:** Implement inline in this session. TDD. Do not rewrite reviewed baskets.

**Goal:** Add a prior-session fade-then-rechase score penalty and split miss tags for setup-penalized limit-up vs near-cutoff names.

**Architecture:** Pure helpers on prior close returns plus `classify_missed_mover` / `_attribution_for_pick`. Ranking calls the helper after same-day chase. Persistence schema unchanged.

**Tech Stack:** Python 3.11 unittest, existing SQLite review bundle, Evidence Console labels.

## Global Constraints

- GitHub issue #21 is the spec.
- No new dependencies.
- Atomic snapshot/review publication unchanged.
- Reviewed baskets remain immutable.
- `python` is `D:\miniconda3\python.exe`.

---

### Task 1: Penalty helper and miss tags

**Files:** `stock_expert/config.py`, `stock_expert/services.py`, `tests/test_services.py`, frontend labels, docs.

- [x] Spec saved
- [x] Failing tests then implementation
- [x] Docs + PR
