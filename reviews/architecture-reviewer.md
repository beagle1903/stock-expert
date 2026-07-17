# Architecture Review

## Scope

Reviewed repository guidance, architecture/decision/feature docs, all production modules, tests, the local routine plugin, `git status`, recent history, and the integrity-focused changes in `48dd62a`. Ran all 93 unit tests successfully.

## Findings

### P1 — Yahoo imports mutate published daily snapshots

Evidence: `stock_expert/yahoo.py:187-190` and `:265-266` send five-field rows to `upsert_prices`. `stock_expert/database.py:395-423` resolves those rows to the latest existing snapshot for each date without considering `source_label`; `:436-445` then updates conflicting stock rows in place.

Impact: if a `daily_csv` snapshot already exists, an optional Yahoo import can overwrite its price basis after publication while leaving its `market_snapshots` rows unchanged. Picks, review returns, and historical evidence can therefore change without a new snapshot run, contradicting the documented atomic/immutable snapshot model.

Suggested fix: make every ingestion publish a source-owned `snapshot_run` and immutable child rows. Require an explicit snapshot id in the low-level writer; remove the legacy “find latest snapshot of any source” behavior. Define whether Yahoo history is a separate dataset/read model or a selectable snapshot source.

### P1 — Idempotent review persistence is not idempotent review output

Evidence: `stock_expert/services.py:1015-1126` recomputes picks, results, attribution, movers, and weights from current “latest” snapshots before attempting the idempotent insert. On conflict only weights are reloaded (`:1127-1133`). `get_review_run` returns only id and weights (`stock_expert/database.py:679-691`), while the response continues to emit recomputed data (`stock_expert/services.py:1135-1173`).

Impact: rerunning a persisted review after a new same-date import or strategy-code change can display performance and attribution that disagree with the immutable `review_runs`, `review_pick_results`, and `candidate_outcomes` rows. It can even report `no_prior_picks` although a review already exists.

Suggested fix: check for an existing review first. For a persisted rerun, hydrate the complete response from review-owned tables and recorded snapshot/version metadata. Keep current-strategy recomputation behind an explicit dry-run/comparison path.

### P1 — Upgrade migration does not establish the declared candidate ownership

Evidence: fresh schema declares `candidate_outcomes.review_run_id NOT NULL` with a foreign key (`stock_expert/database.py:118-137`), but upgrades only execute `ALTER TABLE ... ADD COLUMN review_run_id INTEGER` (`:278-286`). Existing outcomes are neither backfilled nor table-rebuilt, and duplicate review cleanup removes only pick results and review runs (`:288-305`).

Impact: upgraded production databases retain nullable, unowned candidate evidence and no actual foreign-key constraint on that column. This diverges from fresh installs and from the documented review-owned immutable evidence model.

Suggested fix: implement a transactional, versioned table-rebuild migration: map legacy outcomes to the retained review run, validate orphan/duplicate policy, copy into the canonical NOT NULL/FK table, swap tables, and assert `PRAGMA foreign_key_check` plus schema shape in migration tests.

### P2 — Snapshot ownership is not database-enforced

Evidence: `stocks`, `signals`, `picks`, and `market_snapshots` declare `snapshot_id` but no foreign key to `snapshot_runs` (`stock_expert/database.py:22-86`). Only review child tables declare ownership FKs (`:106-137`).

Impact: low-level calls can create orphan rows or associate rows with a snapshot of the wrong date/source. Application conventions carry an integrity rule central to nearly every read path.

Suggested fix: rebuild child tables with `FOREIGN KEY (snapshot_id) REFERENCES snapshot_runs(id)` and suitable delete semantics; validate row date equals the parent snapshot date in the repository layer or remove redundant child dates.

### P2 — Ranking cache identity is underspecified

Evidence: `RankingContext` caches only by `date` (`stock_expert/services.py:46-48`, `:262-272`), although ranking depends on database path, latest snapshot id, settings thresholds, and effective weights.

Impact: reuse across settings/databases or after a same-day import silently returns stale/wrong rankings. The CLI currently scopes it safely, but the service API does not encode that invariant.

Suggested fix: key cache entries by immutable ranking inputs (database identity, snapshot id, weight date/version, settings fingerprint), or make the context a routine object bound to one settings instance and captured snapshot set.

## Reviewed With No Architecture Finding

- Daily CSV run + market/price publication is one transaction and rollback behavior is tested.
- Review run, weights, pick results, and new candidate outcomes commit atomically.
- Shared trading-calendar routing replaced duplicated weekday logic cleanly.
- Branch-aware database isolation and the routine-scoped cache fit the documented operator workflow.
- CLI/plugin command routing remains thin and delegates business work to package services.

## P0

No P0 architecture findings.
