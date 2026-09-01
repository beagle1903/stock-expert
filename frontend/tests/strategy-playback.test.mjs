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

test("warns that a partial pilot comparison is not a fair pair", () => {
  const notices = playbackNotices(fixture({
    pilotComparison: { status: "partial" },
  }));

  assert.equal(notices.length, 1);
  assert.match(notices[0], /incomplete/i);
  assert.match(notices[0], /not a fair pair/i);
});
