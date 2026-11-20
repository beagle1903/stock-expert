import assert from "node:assert/strict";
import test from "node:test";

import {
  latestBasketSignalWindowNotice,
  signalWindowNotice,
} from "../src/data/signalWindowViewModel.mjs";

function gapWindow(overrides = {}) {
  return {
    status: "gap",
    windowBars: 6,
    windowStart: "2026-11-10",
    windowEnd: "2026-11-18",
    missingSessions: ["2026-11-12", "2026-11-13"],
    nonSessionDates: [],
    affectedComponents: ["momentum", "volume"],
    ...overrides,
  };
}

test("gap window names the window, missing sessions, components, and degraded evidence", () => {
  const notice = signalWindowNotice(gapWindow());

  assert.equal(notice.tone, "partial");
  assert.equal(notice.label, "Window gap");
  assert.match(notice.text, /^Signal window 2026-11-10 to 2026-11-18/);
  assert.match(notice.text, /2 trading sessions: 2026-11-12, 2026-11-13\./);
  assert.match(notice.text, /momentum and volume baseline/);
  assert.doesNotMatch(notice.text, /non-session/i);
  assert.match(notice.text, /Scores are unchanged; treat this basket as degraded evidence\.$/);
});

test("gap window uses singular wording for one missing session", () => {
  const notice = signalWindowNotice(gapWindow({
    missingSessions: ["2026-11-12"],
    affectedComponents: ["momentum"],
  }));

  assert.match(notice.text, /1 trading session: 2026-11-12\./);
  assert.match(notice.text, /Affected component: momentum\./);
});

test("gap window lists up to five missing sessions in full", () => {
  const missing = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"];
  const notice = signalWindowNotice(gapWindow({ missingSessions: missing }));

  assert.match(notice.text, new RegExp(`5 trading sessions: ${missing.join(", ")}\\.`));
  assert.doesNotMatch(notice.text, /more/);
});

test("gap window truncates more than five missing sessions to the first three", () => {
  const notice = signalWindowNotice(gapWindow({
    windowStart: "2026-10-28",
    missingSessions: [
      "2026-10-29",
      "2026-10-30",
      "2026-11-03",
      "2026-11-04",
      "2026-11-05",
      "2026-11-06",
      "2026-11-07",
    ],
  }));

  assert.match(notice.text, /7 trading sessions: 2026-10-29, 2026-10-30, 2026-11-03 \+4 more\./);
  assert.doesNotMatch(notice.text, /2026-11-04/);
});

test("gap window names non-session snapshot dates", () => {
  const notice = signalWindowNotice(gapWindow({
    missingSessions: ["2026-11-12"],
    nonSessionDates: ["2026-11-15"],
  }));

  assert.match(notice.text, /1 trading session: 2026-11-12\./);
  assert.match(notice.text, /non-session snapshot date: 2026-11-15\./);
});

test("gap window with only non-session dates still explains the gap", () => {
  const notice = signalWindowNotice(gapWindow({
    missingSessions: [],
    nonSessionDates: ["2026-11-15", "2026-11-16"],
  }));

  assert.match(notice.text, /^Signal window 2026-11-10 to 2026-11-18 includes 2 non-session snapshot dates: 2026-11-15, 2026-11-16\./);
  assert.doesNotMatch(notice.text, /trading session/);
});

test("gap window spells out every affected component in readable words", () => {
  const notice = signalWindowNotice(gapWindow({
    affectedComponents: ["momentum", "volume", "fade_then_rechase"],
  }));

  assert.match(notice.text, /Affected components: momentum, volume baseline, and fade-then-rechase\./);
  assert.doesNotMatch(notice.text, /fade_then_rechase/);
});

test("gap window tolerates missing arrays and window bounds", () => {
  const notice = signalWindowNotice({ status: "gap", windowStart: null, windowEnd: null });

  assert.equal(notice.tone, "partial");
  assert.match(notice.text, /^Signal window does not cover contiguous trading sessions\./);
  assert.doesNotMatch(notice.text, /Affected/);
  assert.match(notice.text, /Scores are unchanged; treat this basket as degraded evidence\.$/);
});

test("not captured window reports pre-feature publication neutrally", () => {
  assert.deepEqual(signalWindowNotice({
    status: "not_captured",
    windowBars: null,
    windowStart: null,
    windowEnd: null,
    missingSessions: [],
    nonSessionDates: [],
    affectedComponents: [],
  }), {
    tone: "neutral",
    label: "Window not captured",
    text: "This basket was published before signal-window coverage was recorded.",
  });
});

test("contiguous, absent, and unknown windows produce no notice", () => {
  assert.equal(signalWindowNotice(gapWindow({
    status: "contiguous",
    missingSessions: [],
    affectedComponents: [],
  })), null);
  assert.equal(signalWindowNotice(undefined), null);
  assert.equal(signalWindowNotice(null), null);
  assert.equal(signalWindowNotice({ status: "something_new" }), null);
  assert.equal(signalWindowNotice({}), null);
});

test("latest basket treats an absent window as not captured", () => {
  assert.equal(latestBasketSignalWindowNotice(undefined).label, "Window not captured");
  assert.equal(latestBasketSignalWindowNotice(null).label, "Window not captured");
  assert.equal(latestBasketSignalWindowNotice(gapWindow()).label, "Window gap");
  assert.equal(latestBasketSignalWindowNotice({ status: "contiguous" }), null);
  assert.equal(latestBasketSignalWindowNotice({ status: "something_new" }), null);
});
