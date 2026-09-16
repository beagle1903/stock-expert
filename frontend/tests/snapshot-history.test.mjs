import assert from "node:assert/strict";
import test from "node:test";

import { appContentMode } from "../src/data/strategyEvidenceViewModel.mjs";
import {
  mappingFailureIncreaseNotice,
  persistedRowsLabel,
  snapshotNotices,
} from "../src/data/snapshotHistoryViewModel.mjs";

function detail(overrides = {}) {
  return {
    id: 12,
    snapshotDate: "2026-04-21",
    provenanceStatus: "captured",
    publicationResult: "published",
    rowsRead: 640,
    comparison: {
      status: "available",
      priorSnapshotId: 11,
      coverageRegression: false,
      mappingFailureIncrease: false,
      deltas: null,
    },
    ...overrides,
  };
}

test("routes Snapshots independently of latest picks", () => {
  assert.equal(appContentMode("snapshots", false), "snapshot_history");
  assert.equal(appContentMode("snapshots", true), "snapshot_history");
});

test("explains snapshots that never captured provenance", () => {
  const notices = snapshotNotices(detail({
    provenanceStatus: "not_captured",
    rowsRead: null,
    comparison: {
      status: "not_captured",
      priorSnapshotId: 11,
      coverageRegression: false,
      mappingFailureIncrease: false,
      deltas: null,
    },
  }));
  assert.equal(notices.includes("Provenance was not captured for this snapshot."), true);
});

test("explains the first published snapshot has no prior comparison", () => {
  const notices = snapshotNotices(detail({
    comparison: {
      status: "unavailable",
      priorSnapshotId: null,
      coverageRegression: false,
      mappingFailureIncrease: false,
      deltas: null,
    },
  }));
  assert.equal(notices.includes("No prior published snapshot."), true);
});

test("labels coverage regression against the prior published snapshot id", () => {
  const notices = snapshotNotices(detail({
    comparison: {
      status: "available",
      priorSnapshotId: 11,
      coverageRegression: true,
      mappingFailureIncrease: false,
      deltas: { tickerCoverage: -0.04 },
    },
  }));
  assert.equal(notices.includes("Coverage is lower than snapshot #11."), true);
});

test("labels mapping-failure increases against the prior published snapshot id", () => {
  assert.equal(
    mappingFailureIncreaseNotice(11),
    "Unmapped rows increased versus snapshot #11.",
  );
  const notices = snapshotNotices(detail({
    comparison: {
      status: "available",
      priorSnapshotId: 11,
      coverageRegression: false,
      mappingFailureIncrease: true,
      deltas: { skippedUnmappedCount: 2 },
    },
  }));
  assert.equal(notices.includes("Unmapped rows increased versus snapshot #11."), true);
});

test("labels persisted market-row counts as persisted rows", () => {
  assert.equal(persistedRowsLabel(), "Persisted rows");
  assert.equal(/csv/i.test(persistedRowsLabel()), false);
  assert.equal(/rows read/i.test(persistedRowsLabel()), false);
});
