import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_STOCK_EXPERT_API_PORT,
  resolveStockExpertApiPort,
} from "../config/local-api.mjs";

test("uses the safe local API default", () => {
  assert.equal(DEFAULT_STOCK_EXPERT_API_PORT, 18765);
  assert.equal(resolveStockExpertApiPort({}), "18765");
});

test("accepts a valid API port override", () => {
  assert.equal(resolveStockExpertApiPort({ STOCK_EXPERT_API_PORT: " 19001 " }), "19001");
});

test("rejects invalid API port overrides", () => {
  for (const value of ["abc", "0", "65536", "18.5"]) {
    assert.throws(
      () => resolveStockExpertApiPort({ STOCK_EXPERT_API_PORT: value }),
      /integer between 1 and 65535/,
    );
  }
});
