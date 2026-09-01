import assert from "node:assert/strict";
import test from "node:test";

import { playbackNotices } from "../src/data/strategyPlaybackViewModel.mjs";

function fixture(overrides = {}) {
  return {
    signal: { status: "available" },
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
    basket: { attributionStatus: "partial" },
    pilotComparison: { status: "unavailable" },
  }));

  assert.equal(notices.length, 3);
  assert.match(notices[0], /exact signal snapshot/i);
  assert.match(notices[1], /lack stored candidate attribution/i);
  assert.match(notices[2], /no paired pilot session/i);
});
