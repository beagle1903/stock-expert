# Backlog

- [x] Make `review` idempotent for the same date
- [x] Remove derived ticker fallback for unmapped CSV rows
- [ ] Add/import a real symbol/code column so fewer CSV rows depend on `ticker_map.csv`
- [x] Make `picks` use richer snapshot fields directly through setup penalties
- [x] Add richer snapshot attribution to `review` output
- [ ] Keep Yahoo import as an optional secondary data path
- [x] Add a launcher-owned post-boot watchdog that observes new and reused UI/API processes for at least five minutes, tails ignored logs, checks direct/proxied endpoints and persisted-basket semantics, and writes early operator failure summaries; keep browser-console inspection as a complementary run-skill check.
