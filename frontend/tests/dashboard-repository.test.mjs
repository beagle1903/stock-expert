import assert from "node:assert/strict";
import test from "node:test";

import { dashboardRepository } from "../src/data/dashboardRepository.ts";
import { dashboardBootKind } from "../src/data/dashboardViewModel.mjs";

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function dashboardPayload() {
  return {
    signalDate: "2026-04-21",
    tradeDate: "2026-04-22",
    snapshot: {
      id: 12,
      importedAt: "2026-04-21 18:00",
      source: "daily_csv",
      status: "persisted",
      priceBasis: "previous_close_to_latest",
    },
    exposure: {
      universeCount: 10,
      advancerRatio: 0.5,
      pickCountCap: 5,
      policy: "normal",
    },
    picks: [{
      rank: 1,
      ticker: "THYAO",
      score: 1.1,
      risk: "medium",
      horizon: "intraday",
      selectionBucket: "score_ranked",
      signals: {
        momentum: 1,
        volume: 1,
        technical: 0,
        fundamental: 0,
        quality: 0,
        setupPenalty: 0,
        maTrend: 1,
        liquidity: 1,
        totalBoost: 0,
        netAdjustment: 0,
      },
    }],
    runSteps: [{ id: 1, label: "Import", detail: "daily_csv" }],
  };
}

function reviewPayload() {
  return {
    id: 7,
    signalDate: "2026-04-20",
    reviewDate: "2026-04-21",
    averageReturn: 0.01,
    winRate: 0.5,
    wins: 1,
    pickCount: 2,
    minimumWinReturn: 0.02,
    outcomes: [],
    missedMoversStatus: "not_captured",
    missedMovers: [],
  };
}

test("load merges latest picks, review, and history into DashboardData", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url === "/api/picks/latest") {
      return jsonResponse(200, { dashboard: dashboardPayload() });
    }
    if (url === "/api/reviews/latest") {
      return jsonResponse(200, { review: reviewPayload() });
    }
    if (url === "/api/reviews/history") {
      return jsonResponse(200, {
        reviews: [{
          id: 7,
          signalDate: "2026-04-20",
          reviewDate: "2026-04-21",
          averageReturn: 0.01,
          winRate: 0.5,
          wins: 1,
          pickCount: 2,
        }],
      });
    }
    throw new Error(`unexpected ${url}`);
  };
  try {
    const data = await dashboardRepository.load();
    assert.deepEqual(calls.sort(), [
      "/api/picks/latest",
      "/api/reviews/history",
      "/api/reviews/latest",
    ]);
    assert.equal(data.snapshot.id, 12);
    assert.equal(data.picks[0].ticker, "THYAO");
    assert.equal(data.review.id, 7);
    assert.equal(data.reviewHistory.length, 1);
    assert.equal(data.reviewHistory[0].id, 7);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("load throws on a non-OK picks response", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (url === "/api/picks/latest") {
      return jsonResponse(503, { error: "picks API down" });
    }
    return jsonResponse(200, url === "/api/reviews/latest" ? { review: null } : { reviews: [] });
  };
  try {
    await assert.rejects(dashboardRepository.load(), /picks API down/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("load throws when the picks payload has no dashboard", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (url === "/api/picks/latest") {
      return jsonResponse(200, { dashboard: null });
    }
    return jsonResponse(200, url === "/api/reviews/latest" ? { review: null } : { reviews: [] });
  };
  try {
    await assert.rejects(dashboardRepository.load(), /No persisted snapshot is available yet/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("boot kind never maps API error to empty basket", () => {
  assert.equal(dashboardBootKind("error", false), "error");
  assert.equal(dashboardBootKind("error", true), "error");
  assert.equal(dashboardBootKind("loading", false), "loading");
  assert.equal(dashboardBootKind("loaded", false), "empty");
  assert.equal(dashboardBootKind("loaded", true), "ready");
});
