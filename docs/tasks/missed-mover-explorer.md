# Missed-Mover Explorer Plan

Status: implemented on `codex/missed-mover-explorer` on 2026-08-30.

## Goal

Make each persisted review answer: which leading movers were missed, which were
actionable, and what point-in-time evidence explains their exclusion.

## Product Scope

- Add an explorer to the Reviews screen for the selected review.
- List at most the 12 missed movers already considered by review logic.
- Filter by `all`, `actionable`, and `non_actionable`.
- Show ticker, realized return, classification, reason, candidate rank, and
  selection note.
- Show signal components, boosts, and setup penalty when ranked evidence exists.
- Preserve the current picked-outcomes panel and compact review navigation.
- Provide explicit states for no misses, loading/error, and historical evidence
  that was not captured.

## Persistence Decision

Add `review_missed_mover_results`, owned by `review_runs`. Persist the review's
ordered missed-mover rows in the same transaction as pick results, candidate
outcomes, weights, and pilot results.

Store the realized return, mover order, actionability, reason, attribution data
status, candidate rank, selection note, selection bucket, signal components,
total boost, and net adjustment. This freezes the evidence and classification
used by that review instead of recalculating history with later settings or a
newer target-date snapshot.

Existing review runs will not be silently recomputed. Their detail response will
report `not_captured`; deterministic backfill is a separate future decision.

## Implementation Slices

1. **Database**
   - Add the owned table, foreign key, and review-order index.
   - Extend `persist_review_bundle` to insert missed movers atomically.
   - Keep reruns idempotent and existing review evidence immutable.
2. **Review service**
   - Pass the already-built missed-mover entries into persistence.
   - Preserve current classification, weight adjustment, and CLI JSON behavior.
3. **Web API**
   - Extend review-detail serialization with `missedMoversStatus` and
     `missedMovers`.
   - Keep `/api/reviews/history` summary-only; selected detail owns the larger
     payload.
4. **Frontend**
   - Add typed missed-mover models and a filterable list/detail explorer.
   - Make exclusion reasons readable without inventing recommendations.
   - Retain keyboard focus, responsive layout, and explicit price-basis labels.
5. **Verification and documentation**
   - Add database rollback/idempotency and service-classification tests.
   - Add web serialization tests for captured, empty, and legacy-not-captured
     reviews.
   - Run Python unit tests, frontend build/tests, and browser QA.
   - Update `docs/features/review.md`, `docs/features/dashboard.md`, architecture,
     current task, and durable memory when implementation lands.

## Out of Scope For V1

- Strategy, scoring, thresholds, weight adjustment, or pick-count changes.
- Reclassifying or backfilling old reviews.
- Live quotes, alerts, portfolios, order execution, or personalized advice.
- Strategy Evidence Lab charts or historical playback.

## Done When

- A newly persisted review stores missed-mover evidence in its review transaction.
- Selecting that review displays stable actionable/non-actionable evidence and
  attribution after restart.
- Repeating the review cannot replace its captured rows.
- Older reviews clearly report that missed-mover evidence was not captured.
- Failure while inserting missed movers rolls back the entire review bundle.
- Relevant tests, frontend build, browser QA, and documentation pass.

## Verification Record

- Python: 148 tests passed.
- Trace: 92.61% weighted production-line coverage (3,472/3,749 lines).
- Frontend: production build passed; 10 Node tests passed.
- Browser: captured and legacy states, both classification filters, desktop and
  390px responsive layouts, horizontal overflow, and console errors checked.
