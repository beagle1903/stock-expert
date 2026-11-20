import assert from "node:assert/strict";
import test from "node:test";

import { playbackNotices } from "../src/data/strategyPlaybackViewModel.mjs";

function fixture(overrides = {}) {
  return {
    signal: { status: "available" },
    strategy: { weightsStatus: "available" },
    basket: { attributionStatus: "available" },
    pilotComparison: { status: "available" },
    ...overrides,
  };
}

test("keeps complete playback free of evidence warnings", () => {
  assert.deepEqual(playbackNotices(fixture()), []);
});

test("explains legacy and partial evidence without recomputation", () => {
  const notices = playbackNotices(fixture({
    signal: { status: "unavailable" },
    strategy: { weightsStatus: "unavailable" },
    basket: { attributionStatus: "partial" },
    pilotComparison: { status: "unavailable" },
  }));

  assert.equal(notices.length, 4);
  assert.match(notices[0], /exact signal snapshot/i);
  assert.match(notices[1], /persisted weights/i);
  assert.match(notices[2], /lack stored candidate attribution/i);
  assert.match(notices[3], /no paired pilot session/i);
});

test("adds the signal-window gap notice to playback", () => {
  const notices = playbackNotices(fixture({
    signal: {
      status: "available",
      signalWindow: {
        status: "gap",
        windowBars: 6,
        windowStart: "2026-11-10",
        windowEnd: "2026-11-18",
        missingSessions: ["2026-11-12", "2026-11-13"],
        nonSessionDates: [],
        affectedComponents: ["momentum", "volume"],
      },
    },
  }));

  assert.equal(notices.length, 1);
  assert.match(notices[0], /^Signal window 2026-11-10 to 2026-11-18/);
  assert.match(notices[0], /2026-11-12, 2026-11-13/);
  assert.match(notices[0], /degraded evidence/);
});

test("keeps not-captured, contiguous, and absent signal windows out of playback notices", () => {
  const empty = {
    windowBars: null,
    windowStart: null,
    windowEnd: null,
    missingSessions: [],
    nonSessionDates: [],
    affectedComponents: [],
  };
  assert.deepEqual(playbackNotices(fixture({
    signal: { status: "available", signalWindow: { ...empty, status: "not_captured" } },
  })), []);
  assert.deepEqual(playbackNotices(fixture({
    signal: { status: "available", signalWindow: { ...empty, status: "contiguous" } },
  })), []);
  assert.deepEqual(playbackNotices(fixture({ signal: { status: "available" } })), []);
});

test("warns that a partial pilot comparison is not a fair pair", () => {
  const notices = playbackNotices(fixture({
    pilotComparison: { status: "partial" },
  }));

  assert.equal(notices.length, 1);
  assert.match(notices[0], /incomplete/i);
  assert.match(notices[0], /not a fair pair/i);
});
