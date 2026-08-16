import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  DEFAULT_INTERVAL_MS,
  MINIMUM_OBSERVATION_MS,
  inspectWebApp,
  observeWebApp,
  resolveWatchdogConfig,
  scanLogUpdates,
  validateOperationalDashboard,
} from "../scripts/watchdog.mjs";

const testRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", ".test_tmp", "watchdog-tests");
mkdirSync(testRoot, { recursive: true });

function dashboardPayload(overrides = {}) {
  return {
    dashboard: {
      signalDate: "2026-08-14",
      tradeDate: "2026-08-17",
      snapshot: { id: 121, status: "persisted", source: "daily_csv" },
      exposure: { pickCountCap: 3 },
      picks: [
        { rank: 1, ticker: "AAA" },
        { rank: 2, ticker: "BBB" },
        { rank: 3, ticker: "CCC" },
      ],
      ...overrides,
    },
  };
}

async function listen(handler) {
  const server = createServer(handler);
  await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
  return server;
}

function close(server) {
  return new Promise((resolveClose) => server.close(resolveClose));
}

test("production defaults enforce a five-minute observation at a 15-30 second interval", () => {
  const config = resolveWatchdogConfig({});
  assert.equal(config.durationMs, MINIMUM_OBSERVATION_MS);
  assert.equal(config.intervalMs, DEFAULT_INTERVAL_MS);
  assert.throws(
    () => resolveWatchdogConfig({ STOCK_EXPERT_WATCHDOG_DURATION_MS: "1000" }),
    /cannot be shorter than five minutes/,
  );
  assert.equal(resolveWatchdogConfig({
    STOCK_EXPERT_WATCHDOG_ALLOW_SHORT: "1",
    STOCK_EXPERT_WATCHDOG_DURATION_MS: "25",
    STOCK_EXPERT_WATCHDOG_INTERVAL_MS: "5",
  }).durationMs, 25);
});

test("semantic validation rejects empty, duplicate, and repair-snapshot baskets", () => {
  assert.deepEqual(validateOperationalDashboard(dashboardPayload()), []);
  const invalid = dashboardPayload({
    snapshot: { id: 122, status: "persisted", source: "yahoo_history_browser" },
    picks: [{ rank: 1, ticker: "AAA" }, { rank: 2, ticker: "AAA" }],
  });
  const codes = new Set(validateOperationalDashboard(invalid).map((failure) => failure.code));
  assert.ok(codes.has("repair_snapshot_selected"));
  assert.ok(codes.has("invalid_operational_basket"));
  assert.equal(validateOperationalDashboard({ dashboard: null })[0].code, "missing_operational_basket");
});

test("log scanning reports only newly appended runtime errors", () => {
  const logPath = resolve(testRoot, `runtime-${process.pid}.log`);
  writeFileSync(logPath, "old Error: already handled\n", "utf8");
  const offsets = { [logPath]: Buffer.byteLength("old Error: already handled\n") };
  assert.deepEqual(scanLogUpdates([logPath], offsets), []);
  writeFileSync(logPath, "Traceback: new API failure\n", { encoding: "utf8", flag: "a" });
  assert.equal(scanLogUpdates([logPath], offsets)[0].code, "runtime_log_error");
});

test("real HTTP inspection validates direct and Vite-proxied dashboard boundaries", async (t) => {
  let apiPort;
  const api = await listen((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/health") response.end(JSON.stringify({ ok: true, apiPort }));
    else if (request.url === "/api/picks/latest") response.end(JSON.stringify(dashboardPayload()));
    else if (request.url === "/api/reviews/latest") response.end(JSON.stringify({ review: null }));
    else if (request.url === "/api/reviews/history") response.end(JSON.stringify({ reviews: [] }));
    else { response.statusCode = 404; response.end("{}"); }
  });
  apiPort = api.address().port;
  const ui = await listen(async (request, response) => {
    if (request.url === "/") return response.end("<title>Stock Expert · Evidence Console</title>");
    const proxied = await fetch(`http://127.0.0.1:${apiPort}${request.url}`);
    response.statusCode = proxied.status;
    response.setHeader("Content-Type", "application/json");
    response.end(await proxied.text());
  });
  t.after(async () => { await Promise.all([close(api), close(ui)]); });

  const result = await inspectWebApp({
    uiBaseUrl: `http://127.0.0.1:${ui.address().port}`,
    apiBaseUrl: `http://127.0.0.1:${apiPort}`,
    apiPort,
  });
  assert.equal(result.ok, true);
  assert.equal(result.snapshotId, 121);
});

test("real HTTP inspection detects proxy port drift", async (t) => {
  let apiPort;
  const api = await listen((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/health") response.end(JSON.stringify({ ok: true, apiPort }));
    else if (request.url === "/api/picks/latest") response.end(JSON.stringify(dashboardPayload()));
    else if (request.url === "/api/reviews/latest") response.end(JSON.stringify({ review: null }));
    else if (request.url === "/api/reviews/history") response.end(JSON.stringify({ reviews: [] }));
    else { response.statusCode = 404; response.end("{}"); }
  });
  apiPort = api.address().port;
  const ui = await listen(async (request, response) => {
    response.setHeader("Content-Type", request.url === "/" ? "text/html" : "application/json");
    if (request.url === "/") return response.end("<title>Stock Expert · Evidence Console</title>");
    if (request.url === "/api/health") return response.end(JSON.stringify({ ok: true, apiPort: apiPort + 1 }));
    const proxied = await fetch(`http://127.0.0.1:${apiPort}${request.url}`);
    response.end(await proxied.text());
  });
  t.after(async () => { await Promise.all([close(api), close(ui)]); });

  const result = await inspectWebApp({
    uiBaseUrl: `http://127.0.0.1:${ui.address().port}`,
    apiBaseUrl: `http://127.0.0.1:${apiPort}`,
    apiPort,
  });
  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.code === "proxy_port_mismatch"));
});

test("real HTTP inspection detects an exited API process", async (t) => {
  const api = await listen((_request, response) => response.end("{}"));
  const exitedPort = api.address().port;
  await close(api);
  const ui = await listen((request, response) => {
    if (request.url === "/") return response.end("<title>Stock Expert · Evidence Console</title>");
    response.statusCode = 502;
    response.end("{}");
  });
  t.after(async () => { await close(ui); });

  const result = await inspectWebApp({
    uiBaseUrl: `http://127.0.0.1:${ui.address().port}`,
    apiBaseUrl: `http://127.0.0.1:${exitedPort}`,
    apiPort: exitedPort,
  });
  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.code === "directHealth_unhealthy"));
});

test("observation fails immediately with a clear runtime-log summary", async (t) => {
  let apiPort;
  const api = await listen((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/api/health") response.end(JSON.stringify({ ok: true, apiPort }));
    else if (request.url === "/api/picks/latest") response.end(JSON.stringify(dashboardPayload()));
    else if (request.url === "/api/reviews/latest") response.end(JSON.stringify({ review: null }));
    else if (request.url === "/api/reviews/history") response.end(JSON.stringify({ reviews: [] }));
    else { response.statusCode = 404; response.end("{}"); }
  });
  apiPort = api.address().port;
  const ui = await listen(async (request, response) => {
    if (request.url === "/") return response.end("<title>Stock Expert · Evidence Console</title>");
    const proxied = await fetch(`http://127.0.0.1:${apiPort}${request.url}`);
    response.end(await proxied.text());
  });
  t.after(async () => { await Promise.all([close(api), close(ui)]); });
  const suffix = `${process.pid}-${Date.now()}`;
  const logPath = resolve(testRoot, `observe-${suffix}.log`);
  const statusPath = resolve(testRoot, `status-${suffix}.json`);
  const watchdogLogPath = resolve(testRoot, `polls-${suffix}.log`);
  writeFileSync(logPath, "", "utf8");
  let injected = false;
  const fetchWithRuntimeError = async (...args) => {
    if (!injected) {
      injected = true;
      writeFileSync(logPath, "Error: simulated browser runtime failure\n", { flag: "a" });
    }
    return fetch(...args);
  };

  const summary = await observeWebApp({
    uiBaseUrl: `http://127.0.0.1:${ui.address().port}`,
    apiBaseUrl: `http://127.0.0.1:${apiPort}`,
    apiPort,
    logPaths: [logPath],
    statusPath,
    watchdogLogPath,
    config: { allowShort: true, durationMs: 1000, intervalMs: 10, failureThreshold: 2 },
    fetchImpl: fetchWithRuntimeError,
  });
  assert.equal(summary.status, "failed");
  assert.equal(summary.polls, 1);
  assert.match(summary.likelyCause, /logged a runtime\/startup error/);
  assert.match(summary.logTails[logPath].at(-1), /simulated browser runtime failure/);
});
