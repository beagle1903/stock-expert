# Backlog

- [x] Make `review` idempotent for the same date
- [x] Remove derived ticker fallback for unmapped CSV rows
- [ ] Add/import a real symbol/code column so fewer CSV rows depend on `ticker_map.csv`
- [x] Make `picks` use richer snapshot fields directly through setup penalties
- [x] Add richer snapshot attribution to `review` output
- [ ] Keep Yahoo import as an optional secondary data path
- [x] Add a launcher-owned post-boot watchdog that observes new and reused UI/API processes for at least five minutes, tails ignored logs, checks direct/proxied endpoints and persisted-basket semantics, and writes early operator failure summaries; keep browser-console inspection as a complementary run-skill check.

## Enhancement Roadmap

Work through these independently so each feature can be tested and trusted before
the next one begins. The numbers preserve the original idea labels; delivery
starts with item 2.

- [x] **2. Missed-Mover Explorer** — persist and display actionable and non-actionable missed movers, exclusion reasons, candidate rank, signal attribution, and realized return. See `docs/tasks/missed-mover-explorer.md`.
- [x] **1. Strategy Evidence Lab** — expose score-ranked versus bucketed results, pilot thresholds, cutoff analysis, rank bands, breadth, and setup-penalty evidence. See `docs/tasks/strategy-evidence-lab.md`.
- [ ] **4. Historical Strategy Playback** — provide a read-only signal-date view of the preserved basket, evidence, market context, and eventual review outcome.
- [ ] **3. Data Quality & Snapshot History** — persist snapshot provenance and validation metrics, then expose import health, coverage, mapping failures, lineage, and prior-snapshot comparison.

Implementation order after Missed-Mover Explorer remains a deliberate user
choice; roadmap order above reflects estimated implementation cost, not
architectural importance.
