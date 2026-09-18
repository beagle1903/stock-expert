# Live Evidence Panels

Status: implemented on `live-evidence-panels`. Requirement ticket:
[GitHub issue #13](https://github.com/beagle1903/stock-expert/issues/13).

Python ranking, review, import, and SQLite strategy are unchanged. No new
`web_api` routes.

## Inventory

All Evidence Console views already call live loopback APIs:

- Today's Picks / Overview / pick-dependent diagnostics: `/api/picks/latest`
- Reviews: `/api/reviews/latest`, `/api/reviews/history`, `/api/reviews/{id}`,
  `/api/strategy-playback/{review_id}`
- Strategy Lab: `/api/strategy-evidence`
- Snapshots: `/api/snapshots/history`, `/api/snapshots/{id}`
- Data & Runs: existing routine preview/execute loopback API

## Leftover honesty work

- Deleted unused `frontend/src/data/mockDashboard.ts` (zero importers).
- Boot no longer maps `status === "error"` to the empty-basket StatusView.
- Selected ticker starts empty and falls back to `data.picks[0]`; no hardcoded
  ticker.
- `useDashboard` retains the caught error message for the error StatusView.
- `dashboardBootKind` unit-tests error vs empty vs loading vs ready.

## Verification

- `cd frontend && npm test`
- Grep: nothing imports `mockDashboard`.
- API-down Retry must not say "No persisted ideas for this signal date".
- Successful load with no picks still uses that empty copy.
