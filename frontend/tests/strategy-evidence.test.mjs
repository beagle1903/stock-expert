import assert from "node:assert/strict";
import test from "node:test";

import {
  appContentMode,
  createLatestRequestGuard,
  evidenceDisplayState,
  evidenceWindowOptions,
  findEvidencePattern,
  findStrategySummary,
} from "../src/data/strategyEvidenceViewModel.mjs";

function fixture(overrides = {}) {
  return {
    status: "available",
    comparison: {
      status: "available",
      strategies: [
        { strategy: "score_ranked", compoundedReturn: 0.01 },
        { strategy: "bucketed", compoundedReturn: 0.02 },
      ],
    },
    candidateEvidence: {
      status: "available",
      patterns: [
        { pattern: "setup_penalized", count: 4, averageReturn: -0.01, winRate: 0.25 },
      ],
    },
    breadth: { status: "available" },
    ...overrides,
  };
}

test("exposes only supported review windows", () => {
  assert.deepEqual(evidenceWindowOptions, ["5", "10", "20", "all"]);
});

test("accepts results only from the latest evidence request", () => {
  const guard = createLatestRequestGuard();
  const firstRequest = guard.begin();
  const secondRequest = guard.begin();

  assert.equal(guard.isLatest(firstRequest), false);
  assert.equal(guard.isLatest(secondRequest), true);
  guard.invalidate();
  assert.equal(guard.isLatest(secondRequest), false);
});

test("routes Strategy Lab independently of dashboard data", () => {
  assert.equal(appContentMode("diagnostics", false), "strategy_lab");
  assert.equal(appContentMode("picks", false), "dashboard_unavailable");
  assert.equal(appContentMode("picks", true), "dashboard");
});

test("maps empty evidence to the explicit empty state", () => {
  assert.deepEqual(evidenceDisplayState({ status: "empty" }), {
    kind: "empty",
    notices: [],
  });
});

test("maps incomplete evidence to a partial state with scoped notices", () => {
  const state = evidenceDisplayState(fixture({
    comparison: { status: "partial", strategies: [] },
    candidateEvidence: { status: "partial", patterns: [] },
    breadth: { status: "unavailable" },
  }));

  assert.equal(state.kind, "partial");
  assert.equal(state.notices.length, 3);
  assert.match(state.notices[0], /excluded from the comparison/);
  assert.match(state.notices[1], /candidate outcomes/);
  assert.match(state.notices[2], /signal snapshot/);
});

test("maps complete evidence and resolves strategy and setup-penalty rows", () => {
  const evidence = fixture();

  assert.deepEqual(evidenceDisplayState(evidence), { kind: "complete", notices: [] });
  assert.equal(findStrategySummary(evidence, "bucketed").compoundedReturn, 0.02);
  assert.equal(findEvidencePattern(evidence, "setup_penalized").count, 4);
  assert.equal(findEvidencePattern(evidence, "missing"), null);
});
