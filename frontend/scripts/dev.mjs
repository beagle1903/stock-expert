import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const viteEntry = join(frontendRoot, "node_modules", "vite", "bin", "vite.js");
const configuredPython = process.env.STOCK_EXPERT_PYTHON?.trim();
const windowsPython = "D:\\miniconda3\\python.exe";
const python = configuredPython
  || (process.platform === "win32" && existsSync(windowsPython) ? windowsPython : process.platform === "win32" ? "python" : "python3");

const api = spawn(
  python,
  ["-m", "stock_expert.web_api", "--host", "127.0.0.1", "--port", "8765"],
  { cwd: repositoryRoot, env: process.env, stdio: "inherit" },
);
const vite = spawn(process.execPath, [viteEntry, ...process.argv.slice(2)], {
  cwd: frontendRoot,
  env: process.env,
  stdio: "inherit",
});

let closing = false;
function close(exitCode = 0) {
  if (closing) return;
  closing = true;
  if (!api.killed) api.kill();
  if (!vite.killed) vite.kill();
  process.exitCode = exitCode;
}

api.on("error", (error) => {
  console.error(`Routine API failed to start with ${python}: ${error.message}`);
  close(1);
});
vite.on("error", (error) => {
  console.error(`Vite failed to start: ${error.message}`);
  close(1);
});
api.on("exit", (code) => close(code ?? 1));
vite.on("exit", (code) => close(code ?? 1));
process.on("SIGINT", () => close(0));
process.on("SIGTERM", () => close(0));
