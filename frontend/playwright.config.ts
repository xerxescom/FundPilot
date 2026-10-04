import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const frontendDir = process.cwd();
const repoRoot = path.resolve(frontendDir, "..");
const backendPort = 8700;
const frontendPort = 5175;
const backendUrl = `http://127.0.0.1:${backendPort}`;

// Each run gets its own empty scratch database, so the backend always creates a fresh
// schema. Never delete the current run's file here: Playwright re-evaluates this config
// in worker processes, and removing the file mid-run would wipe the live schema.
const databaseDir = path.join(os.tmpdir(), "fundpilot-e2e");
fs.mkdirSync(databaseDir, { recursive: true });
const cutoff = Date.now() - 30 * 60 * 1000;
for (const entry of fs.readdirSync(databaseDir)) {
  const file = path.join(databaseDir, entry);
  if (entry.endsWith(".db") && fs.statSync(file).mtimeMs < cutoff) {
    fs.rmSync(file, { force: true });
  }
}
const databaseFile = path.join(databaseDir, `e2e-${Date.now()}.db`);

const venvPython = [
  path.join(repoRoot, ".venv", "Scripts", "python.exe"),
  path.join(repoRoot, ".venv", "bin", "python"),
].find((candidate) => fs.existsSync(candidate));
// --http h11 avoids the optional httptools dependency, which is broken in this venv on Python 3.14.
const uvicornArgs = `-m uvicorn app.main:app --host 127.0.0.1 --port ${backendPort} --http h11`;
const backendCommand = venvPython
  ? `"${venvPython}" ${uvicornArgs}`
  : `uv run --frozen python ${uvicornArgs}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: backendCommand,
      cwd: repoRoot,
      url: `${backendUrl}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: `sqlite:///${databaseFile.replace(/\\/g, "/")}`,
        AUTO_CREATE_TABLES: "true",
        APP_ENV: "dev",
        ENABLE_SCHEDULER: "false",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      cwd: frontendDir,
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        VITE_API_PROXY_TARGET: backendUrl,
      },
    },
  ],
});
