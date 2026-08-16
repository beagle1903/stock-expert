import { appendFileSync, existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

export const MINIMUM_OBSERVATION_MS = 5 * 60 * 1000;
export const DEFAULT_OBSERVATION_MS = MINIMUM_OBSERVATION_MS;
export const DEFAULT_INTERVAL_MS = 20 * 1000;

const runtimeErrorPattern = /(?:\btraceback\b|\buncaught\b|\bunhandled rejection\b|\beaddrinuse\b|\binternal server error\b|\bproxy error\b|\bfailed to start\b|\broutine api failed\b|\bvite failed\b|(?:^|\s)error:)/i;

function positiveInteger(value, name) {
  if (!/^\d+$/.test(String(value ?? "")) || Number(value) <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return Number(value);
}

export function resolveWatchdogConfig(environment = process.env) {
  const allowShort = environment.STOCK_EXPERT_WATCHDOG_ALLOW_SHORT === "1";
  const durationMs = positiveInteger(
    environment.STOCK_EXPERT_WATCHDOG_DURATION_MS ?? DEFAULT_OBSERVATION_MS,
    "STOCK_EXPERT_WATCHDOG_DURATION_MS",
  );
  const intervalMs = positiveInteger(
    environment.STOCK_EXPERT_WATCHDOG_INTERVAL_MS ?? DEFAULT_INTERVAL_MS,
    "STOCK_EXPERT_WATCHDOG_INTERVAL_MS",
  );
  const failureThreshold = positiveInteger(
    environment.STOCK_EXPERT_WATCHDOG_FAILURE_THRESHOLD ?? 2,
    "STOCK_EXPERT_WATCHDOG_FAILURE_THRESHOLD",
  );
  if (!allowShort && durationMs < MINIMUM_OBSERVATION_MS) {
    throw new Error("The production watchdog observation window cannot be shorter than five minutes");
  }
  if (!allowShort && (intervalMs < 15_000 || intervalMs > 30_000)) {
    throw new Error("The production watchdog interval must stay between 15 and 30 seconds");
  }
  return { allowShort, durationMs, intervalMs, failureThreshold };
}

async function request(url, { json = true, timeoutMs = 5_000, fetchImpl = fetch } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, { signal: controller.signal, cache: "no-store" });
    const body = json ? await response.json().catch(() => null) : await response.text();
    return { ok: response.ok, status: response.status, body };
  } catch (error) {
    return { ok: false, status: 0, body: null, error: error instanceof Error ? error.message : String(error) };
  } finally {
    clearTimeout(timeout);
  }
}

export function validateOperationalDashboard(payload) {
  const failures = [];
  const dashboard = payload?.dashboard;
  if (!dashboard) {
    return [{ code: "missing_operational_basket", message: "No persisted operational picks basket is available." }];
  }
  if (!Number.isInteger(dashboard.snapshot?.id) || dashboard.snapshot.id <= 0) {
    failures.push({ code: "invalid_snapshot", message: "Latest picks did not identify a persisted snapshot." });
  }
  if (dashboard.snapshot?.status !== "persisted") {
    failures.push({ code: "invalid_snapshot_status", message: "Latest picks snapshot is not marked persisted." });
  }
  if (/(?:repair|yahoo|price|history)/i.test(String(dashboard.snapshot?.source ?? ""))) {
    failures.push({ code: "repair_snapshot_selected", message: `Latest picks selected non-operational source '${dashboard.snapshot?.source}'.` });
  }
  if (!Array.isArray(dashboard.picks) || dashboard.picks.length === 0) {
    failures.push({ code: "empty_operational_basket", message: "Latest picks returned an empty operational basket." });
  } else {
    const tickers = dashboard.picks.map((pick) => String(pick?.ticker ?? "").trim());
    if (tickers.some((ticker) => !ticker) || new Set(tickers).size !== tickers.length) {
      failures.push({ code: "invalid_operational_basket", message: "Operational picks contain a missing or duplicate ticker." });
    }
    const ranks = dashboard.picks.map((pick) => pick?.rank);
    if (ranks.some((rank, index) => rank !== index + 1)) {
      failures.push({ code: "invalid_pick_ranks", message: "Operational pick ranks are not contiguous." });
    }
  }
  const cap = dashboard.exposure?.pickCountCap;
  if (!Number.isInteger(cap) || cap < 1 || (Array.isArray(dashboard.picks) && dashboard.picks.length > cap)) {
    failures.push({ code: "invalid_exposure", message: "Operational basket violates its persisted exposure cap." });
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(dashboard.signalDate ?? ""))
      || !/^\d{4}-\d{2}-\d{2}$/.test(String(dashboard.tradeDate ?? ""))
      || dashboard.tradeDate <= dashboard.signalDate) {
    failures.push({ code: "invalid_date_route", message: "Signal and target-trade dates are not a valid forward route." });
  }
  return failures;
}

function validateReviewPayloads(latest, history) {
  const failures = [];
  if (!latest || !("review" in latest)) {
    failures.push({ code: "invalid_latest_review", message: "Latest review response has an invalid shape." });
  }
  if (!history || !Array.isArray(history.reviews)) {
    failures.push({ code: "invalid_review_history", message: "Review history response has an invalid shape." });
  }
  return failures;
}

export function initialLogOffsets(paths) {
  return Object.fromEntries(paths.map((path) => [path, existsSync(path) ? statSync(path).size : 0]));
}

export function scanLogUpdates(paths, offsets) {
  const failures = [];
  for (const path of paths) {
    if (!existsSync(path)) continue;
    const size = statSync(path).size;
    const start = size < (offsets[path] ?? 0) ? 0 : offsets[path] ?? 0;
    if (size <= start) continue;
    const length = Math.min(size - start, 128 * 1024);
    const content = readFileSync(path).subarray(size - length, size).toString("utf8");
    offsets[path] = size;
    const matched = content.split(/\r?\n/).find((line) => runtimeErrorPattern.test(line));
    if (matched) failures.push({ code: "runtime_log_error", message: `${path}: ${matched.trim()}` });
  }
  return failures;
}

export async function inspectWebApp({ uiBaseUrl, apiBaseUrl, apiPort, logPaths = [], logOffsets = {}, fetchImpl = fetch }) {
  const endpoints = {
    ui: request(`${uiBaseUrl}/`, { json: false, fetchImpl }),
    directHealth: request(`${apiBaseUrl}/api/health`, { fetchImpl }),
    proxyHealth: request(`${uiBaseUrl}/api/health`, { fetchImpl }),
    directPicks: request(`${apiBaseUrl}/api/picks/latest`, { fetchImpl }),
    proxyPicks: request(`${uiBaseUrl}/api/picks/latest`, { fetchImpl }),
    latestReview: request(`${apiBaseUrl}/api/reviews/latest`, { fetchImpl }),
    reviewHistory: request(`${apiBaseUrl}/api/reviews/history`, { fetchImpl }),
  };
  const results = Object.fromEntries(await Promise.all(
    Object.entries(endpoints).map(async ([name, promise]) => [name, await promise]),
  ));
  const failures = [];
  if (!results.ui.ok || !String(results.ui.body ?? "").includes("Stock Expert · Evidence Console")) {
    failures.push({ code: "ui_unhealthy", message: `UI liveness failed (${results.ui.status || results.ui.error || "unreachable"}).` });
  }
  for (const name of ["directHealth", "proxyHealth", "directPicks", "proxyPicks", "latestReview", "reviewHistory"]) {
    if (!results[name].ok) failures.push({ code: `${name}_unhealthy`, message: `${name} failed (${results[name].status || results[name].error || "unreachable"}).` });
  }
  if (results.directHealth.ok && results.directHealth.body?.ok !== true) {
    failures.push({ code: "api_health_invalid", message: "Direct API health did not report ok=true." });
  }
  if (results.proxyHealth.ok && results.proxyHealth.body?.ok !== true) {
    failures.push({ code: "proxy_health_invalid", message: "Vite-proxied API health did not report ok=true." });
  }
  if (results.directHealth.ok && results.proxyHealth.ok
      && (results.directHealth.body?.apiPort !== Number(apiPort)
        || results.proxyHealth.body?.apiPort !== Number(apiPort))) {
    failures.push({ code: "proxy_port_mismatch", message: `Direct/proxied API does not match configured port ${apiPort}.` });
  }
  if (results.directPicks.ok) failures.push(...validateOperationalDashboard(results.directPicks.body));
  if (results.proxyPicks.ok) failures.push(...validateOperationalDashboard(results.proxyPicks.body));
  const directSnapshot = results.directPicks.body?.dashboard?.snapshot?.id;
  const proxySnapshot = results.proxyPicks.body?.dashboard?.snapshot?.id;
  if (results.directPicks.ok && results.proxyPicks.ok && directSnapshot !== proxySnapshot) {
    failures.push({ code: "proxy_snapshot_mismatch", message: `Direct snapshot #${directSnapshot} differs from proxied snapshot #${proxySnapshot}.` });
  }
  if (results.latestReview.ok && results.reviewHistory.ok) {
    failures.push(...validateReviewPayloads(results.latestReview.body, results.reviewHistory.body));
  }
  failures.push(...scanLogUpdates(logPaths, logOffsets));
  return { ok: failures.length === 0, failures, snapshotId: directSnapshot ?? null };
}

export function likelyCause(failures) {
  const codes = new Set(failures.map((failure) => failure.code));
  if (codes.has("proxy_port_mismatch") || codes.has("proxy_snapshot_mismatch") || [...codes].some((code) => code.startsWith("proxy") && code.endsWith("unhealthy"))) {
    return "Vite proxy and STOCK_EXPERT_API_PORT are out of sync, or Vite is reusing stale configuration.";
  }
  if (codes.has("repair_snapshot_selected") || codes.has("empty_operational_basket") || codes.has("missing_operational_basket")) {
    return "The latest-picks query selected no valid persisted basket, possibly because a price-only/repair snapshot won the lookup.";
  }
  if (codes.has("runtime_log_error")) return "A UI or API process logged a runtime/startup error; inspect the included log tails.";
  if (codes.has("ui_unhealthy")) return "The Vite server exited, failed to bind port 5173, or a different service owns that port.";
  if ([...codes].some((code) => code.startsWith("direct") && code.endsWith("unhealthy"))) {
    return "The Stock Expert API exited, failed to bind its configured port, or is using a different database/configuration.";
  }
  return "A dashboard semantic invariant failed; inspect the endpoint failure list and log tails.";
}

export function tailFile(path, lineCount = 30) {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8").split(/\r?\n/).filter(Boolean).slice(-lineCount);
}

function writeSummary(path, summary) {
  writeFileSync(path, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
}

export async function observeWebApp({
  uiBaseUrl,
  apiBaseUrl,
  apiPort,
  logPaths,
  statusPath,
  watchdogLogPath,
  config = resolveWatchdogConfig(),
  logOffsets = initialLogOffsets(logPaths),
  now = () => Date.now(),
  sleep = (milliseconds) => new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds)),
  fetchImpl = fetch,
  metadata = {},
}) {
  const startedAtMs = now();
  let consecutiveFailures = 0;
  let polls = 0;
  let latestCheck = null;
  while (now() - startedAtMs < config.durationMs) {
    latestCheck = await inspectWebApp({ uiBaseUrl, apiBaseUrl, apiPort, logPaths, logOffsets, fetchImpl });
    polls += 1;
    consecutiveFailures = latestCheck.ok ? 0 : consecutiveFailures + 1;
    appendFileSync(watchdogLogPath, `${JSON.stringify({ at: new Date(now()).toISOString(), poll: polls, ...latestCheck })}\n`, "utf8");
    const loggedRuntimeError = latestCheck.failures.some((failure) => failure.code === "runtime_log_error");
    if (!latestCheck.ok && (loggedRuntimeError || consecutiveFailures >= config.failureThreshold)) {
      const summary = {
        status: "failed",
        ...metadata,
        observationStartedAt: new Date(startedAtMs).toISOString(),
        finishedAt: new Date(now()).toISOString(),
        durationMs: now() - startedAtMs,
        polls,
        failures: latestCheck.failures,
        likelyCause: likelyCause(latestCheck.failures),
        logTails: Object.fromEntries(logPaths.map((path) => [path, tailFile(path)])),
      };
      writeSummary(statusPath, summary);
      return summary;
    }
    const remaining = config.durationMs - (now() - startedAtMs);
    if (remaining > 0) await sleep(Math.min(config.intervalMs, remaining));
  }
  const summary = {
    status: "passed",
    ...metadata,
    observationStartedAt: new Date(startedAtMs).toISOString(),
    finishedAt: new Date(now()).toISOString(),
    durationMs: now() - startedAtMs,
    polls,
    snapshotId: latestCheck?.snapshotId ?? null,
    failures: [],
    likelyCause: null,
    logTails: {},
  };
  writeSummary(statusPath, summary);
  return summary;
}

export function resolveRuntimePaths(repositoryRoot) {
  const tempRoot = resolve(repositoryRoot, ".test_tmp");
  return {
    tempRoot,
    apiLog: resolve(tempRoot, "web-api.log"),
    uiLog: resolve(tempRoot, "web-ui.log"),
    watchdogLog: resolve(tempRoot, "web-watchdog.log"),
    status: resolve(tempRoot, "web-watchdog-summary.json"),
    session: resolve(tempRoot, "web-launch-session.json"),
    apiPid: resolve(tempRoot, "web-api.pid"),
    uiPid: resolve(tempRoot, "web-ui.pid"),
    launcherPid: resolve(tempRoot, "web-launcher.pid"),
  };
}
