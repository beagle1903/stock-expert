import { execFile, spawn } from "node:child_process";
import { appendFileSync, closeSync, existsSync, mkdirSync, openSync, writeFileSync } from "node:fs";
import net from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { resolveStockExpertApiPort } from "../config/local-api.mjs";
import {
  initialLogOffsets,
  observeWebApp,
  resolveRuntimePaths,
  resolveWatchdogConfig,
  tailFile,
} from "./watchdog.mjs";

const execFileAsync = promisify(execFile);
const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const viteEntry = join(frontendRoot, "node_modules", "vite", "bin", "vite.js");
const windowsPython = "D:\\miniconda3\\python.exe";

function configuredPython(environment = process.env) {
  return environment.STOCK_EXPERT_PYTHON?.trim()
    || (process.platform === "win32" && existsSync(windowsPython) ? windowsPython : process.platform === "win32" ? "python" : "python3");
}

function tcpListening(port, host = "127.0.0.1") {
  return new Promise((resolveListening) => {
    const socket = net.createConnection({ host, port: Number(port) });
    socket.setTimeout(800);
    socket.once("connect", () => { socket.destroy(); resolveListening(true); });
    socket.once("timeout", () => { socket.destroy(); resolveListening(false); });
    socket.once("error", () => resolveListening(false));
  });
}

async function httpHealthy(url, expectedText = null) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2_000), cache: "no-store" });
    if (!response.ok) return false;
    if (expectedText === null) return (await response.json()).ok === true;
    return (await response.text()).includes(expectedText);
  } catch {
    return false;
  }
}

async function listeningPid(port) {
  if (process.platform !== "win32") return null;
  try {
    const { stdout } = await execFileAsync("netstat", ["-ano", "-p", "tcp"], { windowsHide: true });
    const pattern = new RegExp(`^\\s*TCP\\s+[^\\s]*:${port}\\s+[^\\s]+\\s+LISTENING\\s+(\\d+)\\s*$`, "mi");
    const match = stdout.match(pattern);
    return match ? Number(match[1]) : null;
  } catch {
    return null;
  }
}

function startDetached(command, args, { cwd, environment, logPath }) {
  const output = openSync(logPath, "a");
  const child = spawn(command, args, {
    cwd,
    env: environment,
    detached: true,
    windowsHide: true,
    stdio: ["ignore", output, output],
  });
  child.on("error", (error) => {
    appendFileSync(logPath, `[launcher] process failed to start: ${error.message}\n`, "utf8");
  });
  child.unref();
  closeSync(output);
  return child.pid;
}

async function waitForHealthy({ uiUrl, apiUrl, timeoutMs, intervalMs }) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const [ui, api] = await Promise.all([
      httpHealthy(uiUrl, "Stock Expert · Evidence Console"),
      httpHealthy(`${apiUrl}/api/health`),
    ]);
    if (ui && api) return true;
    await new Promise((resolveSleep) => setTimeout(resolveSleep, intervalMs));
  }
  return false;
}

export async function launchAndObserve(environment = process.env) {
  const apiPort = resolveStockExpertApiPort(environment);
  const uiPort = 5173;
  const uiUrl = `http://127.0.0.1:${uiPort}`;
  const apiUrl = `http://127.0.0.1:${apiPort}`;
  const paths = resolveRuntimePaths(repositoryRoot);
  mkdirSync(paths.tempRoot, { recursive: true });
  const logOffsets = initialLogOffsets([paths.uiLog, paths.apiLog]);
  writeFileSync(paths.launcherPid, `${process.pid}\n`, "utf8");

  const [uiHealthy, apiHealthy, uiOccupied, apiOccupied] = await Promise.all([
    httpHealthy(uiUrl, "Stock Expert · Evidence Console"),
    httpHealthy(`${apiUrl}/api/health`),
    tcpListening(uiPort),
    tcpListening(apiPort),
  ]);
  if (!uiHealthy && uiOccupied) throw new Error(`Port ${uiPort} is occupied by an unhealthy/non-Stock-Expert UI process`);
  if (!apiHealthy && apiOccupied) throw new Error(`Port ${apiPort} is occupied by an unhealthy/non-Stock-Expert API process`);
  if (!existsSync(viteEntry)) throw new Error("Vite is missing; run npm ci in frontend before launching Stock Expert");

  const processEnvironment = {
    ...environment,
    PYTHONUNBUFFERED: environment.PYTHONUNBUFFERED ?? "1",
    STOCK_EXPERT_API_PORT: apiPort,
  };
  const ui = { state: uiHealthy ? "reused" : "started", pid: null, log: paths.uiLog };
  const api = { state: apiHealthy ? "reused" : "started", pid: null, log: paths.apiLog };
  if (!apiHealthy) {
    api.pid = startDetached(
      configuredPython(environment),
      ["-m", "stock_expert.web_api", "--host", "127.0.0.1", "--port", apiPort],
      { cwd: repositoryRoot, environment: processEnvironment, logPath: paths.apiLog },
    );
  }
  if (!uiHealthy) {
    ui.pid = startDetached(
      process.execPath,
      [viteEntry, "--host", "127.0.0.1", "--strictPort"],
      { cwd: frontendRoot, environment: processEnvironment, logPath: paths.uiLog },
    );
  }
  if (!ui.pid) ui.pid = await listeningPid(uiPort);
  if (!api.pid) api.pid = await listeningPid(apiPort);
  if (ui.pid) writeFileSync(paths.uiPid, `${ui.pid}\n`, "utf8");
  if (api.pid) writeFileSync(paths.apiPid, `${api.pid}\n`, "utf8");

  const startupTimeoutMs = Number(environment.STOCK_EXPERT_STARTUP_TIMEOUT_MS ?? 60_000);
  const startupIntervalMs = Number(environment.STOCK_EXPERT_STARTUP_INTERVAL_MS ?? 1_000);
  const session = {
    status: "starting",
    startedAt: new Date().toISOString(),
    ui,
    api,
    uiUrl,
    apiUrl,
    apiPort: Number(apiPort),
  };
  writeFileSync(paths.session, `${JSON.stringify(session, null, 2)}\n`, "utf8");
  if (!await waitForHealthy({ uiUrl, apiUrl, timeoutMs: startupTimeoutMs, intervalMs: startupIntervalMs })) {
    throw new Error("UI/API did not become healthy within the startup timeout; inspect .test_tmp/web-ui.log and .test_tmp/web-api.log");
  }

  session.status = "observing";
  session.observationStartedAt = new Date().toISOString();
  writeFileSync(paths.session, `${JSON.stringify(session, null, 2)}\n`, "utf8");
  writeFileSync(paths.status, `${JSON.stringify({ ...session, status: "observing" }, null, 2)}\n`, "utf8");
  return observeWebApp({
    uiBaseUrl: uiUrl,
    apiBaseUrl: apiUrl,
    apiPort,
    logPaths: [paths.uiLog, paths.apiLog],
    statusPath: paths.status,
    watchdogLogPath: paths.watchdogLog,
    config: resolveWatchdogConfig(environment),
    logOffsets,
    metadata: { ui, api, uiUrl, apiUrl, apiPort: Number(apiPort) },
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  launchAndObserve().then((summary) => {
    const label = summary.status === "passed" ? "WATCHDOG PASSED" : "WATCHDOG FAILED";
    console.log(`${label}: ${JSON.stringify(summary)}`);
    process.exitCode = summary.status === "passed" ? 0 : 1;
  }).catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    const paths = resolveRuntimePaths(repositoryRoot);
    const summary = {
      status: "failed",
      phase: "startup",
      finishedAt: new Date().toISOString(),
      failures: [{ code: "startup_failure", message }],
      likelyCause: message,
      logTails: {
        [paths.uiLog]: tailFile(paths.uiLog),
        [paths.apiLog]: tailFile(paths.apiLog),
      },
    };
    mkdirSync(paths.tempRoot, { recursive: true });
    writeFileSync(paths.status, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    console.error(`WATCHDOG FAILED: ${JSON.stringify(summary)}`);
    process.exitCode = 1;
  });
}
