# Data Quality & Snapshot History Design

Requirement ticket: [GitHub issue #11](https://github.com/beagle1903/stock-expert/issues/11).
Branch: `codex/data-quality-snapshot-history`.

## Goal

Make snapshot provenance and import health visible and auditable without
changing strategy, scoring, or publication atomicity.

## Current Gap

`snapshot_runs` stores `id`, `snapshot_date`, `imported_at`, `source_label`,
and `source_dir`. Daily CSV import already computes row counts, ticker
coverage, mapping failures, and skipped/malformed rows, but those values
leave only as CLI JSON. The Evidence Console snapshot panel shows id, source,
and `persisted` status. There is no snapshot-history API. `/api/picks/latest`
selects the newest snapshot that owns picks, not the newest import.

## Alternatives Considered

1. Extend `snapshot_runs` with quality columns plus a capture flag, and add a
   read-only Snapshots view. Selected: matches missed-mover `not_captured`
   and keeps failed bundles unpublished.
2. Persist failed import attempts as non-active rows. Rejected: coverage-gate
   and mid-write failures must not create `snapshot_runs`; publication stays
   all-or-nothing.
3. Recompute quality from current CSVs or later snapshots for old rows.
   Rejected: same future-leakage rule as reviews.

## Persistence

Add nullable quality columns on `snapshot_runs` plus
`provenance_captured INTEGER NOT NULL DEFAULT 0`. Existing rows stay `0`.

Captured columns (same names as import JSON where they already exist):

- `rows_read`, `distinct_tickers`, `mapped_count`
- `skipped_non_equity_count`, `skipped_unmapped_count`, `skipped_malformed_count`
- `ticker_coverage`, `decimal_separator`
- `price_basis`, `source_files_json`

Add `snapshot_mapping_failures` owned by `snapshot_id`:

- `failure_order INTEGER NOT NULL`
- `company_name TEXT NOT NULL`
- primary key `(snapshot_id, failure_order)`
- foreign key to `snapshot_runs(id)`

Store unmapped company names in encounter order, capped at 50. Counts remain
the source of truth when the list is truncated.

`persist_daily_snapshot` writes the run, market rows, prices, quality columns,
and mapping-failure rows in the existing `connect()` transaction. Set
`provenance_captured = 1` only in that path. `create_snapshot_run` and Yahoo
or repair paths stay `not_captured`. Coverage-gate failures still raise
before persist. A failed child write rolls back the whole run.

Do not backfill old snapshots.

## API

Read-only:

- `GET /api/snapshots/history` — newest-first summaries for every published
  `snapshot_runs` row (not pick-filtered).
- `GET /api/snapshots/{id}` — one snapshot, mapping-failure names when
  captured, and comparison with the prior published snapshot (`id < selected`
  order by `id DESC`).

Summary fields: id, snapshotDate, importedAt, source, sourceDir,
provenanceStatus (`captured` | `not_captured`), publicationResult
(`published`). Captured summaries also include counts, coverage, and
`unmappedTruncated`.

Detail adds mappingFailures, and `comparison`:

- `unavailable` when no prior published snapshot exists
- `not_captured` when this or the prior row lacks provenance
- `available` with deltas for coverage, rows_read, distinct_tickers,
  skipped_unmapped_count, skipped_malformed_count

A coverage regression is `ticker_coverage` lower than the prior captured
snapshot. A mapping-failure increase is `skipped_unmapped_count` higher than
that prior. API/UI label those explicitly; they do not block publication
(the 75% gate already did).

Do not invoke ranking or selection. Do not change `/api/picks/latest`
ownership rules.

## UI

Add read-only nav item **Snapshots** (`ViewKey` `snapshots`, `?view=snapshots`).
Keep Data & Runs as the only mutating surface. Reachable without a
latest-picks snapshot, same as Strategy Lab.

Show: history list, selected lineage, coverage, skip counts, mapping-failure
names, prior-snapshot comparison, explicit `not_captured` and no-prior
states. No orders, quotes, forecasts, or target prices.

## Testing And Docs

- Persist captured metrics; rollback leaves no new run or child rows.
- Legacy / `create_snapshot_run` rows serialize `not_captured`.
- Coverage-gate still publishes nothing.
- History includes pick-less imports; detail comparison covers available /
  not_captured / unavailable.
- Frontend tests for captured, not_captured, regression labels, and
  Snapshots view without latest picks.
- Update `docs/features/`, architecture, decisions, current task, backlog,
  and `memory.md`. Keep issue #11 open until the work ships.

## Out Of Scope

Strategy, scoring, weights, pick-count, Investing.com refresh internals,
backfill, failed-attempt rows, trading UI, and deployment.
