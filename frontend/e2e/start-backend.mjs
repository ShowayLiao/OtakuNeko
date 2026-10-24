import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";

const backend = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../backend",
);
const temporary = mkdtempSync(resolve(tmpdir(), "otakuneko-qa-"));
const python = resolve(
  backend,
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python",
);
// Do not inherit .env, provider keys, production DB settings or external integrations.
const env = {};
for (const name of [
  "PATH",
  "Path",
  "SystemRoot",
  "WINDIR",
  "TEMP",
  "TMP",
  "HOME",
  "USERPROFILE",
  "LANG",
]) {
  if (process.env[name]) env[name] = process.env[name];
}
Object.assign(env, {
  PYTHONPATH: backend,
  PYTHONUTF8: "1",
  DEPLOY_MODE: "local",
  DEBUG: "false",
  SQLITE_FILE: resolve(temporary, "qa.db"),
  CHECKPOINT_DB_PATH: resolve(temporary, "checkpoint.db"),
  JWT_SECRET_KEY: randomBytes(32).toString("hex"),
  ENABLE_QB_PROXY: "false",
  ENABLE_PROACTIVE_SCHEDULER: "false",
  OPENAI_API_KEY: "",
  REDIS_URL: "",
});
const child = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8100",
    "--no-access-log",
  ],
  { cwd: temporary, env, stdio: "inherit", windowsHide: true },
);
let stopping = false;
function stop() {
  if (!stopping) {
    stopping = true;
    child.kill("SIGTERM");
  }
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
child.on("error", (error) => {
  console.error(`QA backend failed: ${error.code}`);
  rmSync(temporary, { recursive: true, force: true });
  process.exitCode = 1;
});
child.on("exit", (code) => {
  rmSync(temporary, { recursive: true, force: true });
  process.exitCode = stopping ? 0 : (code ?? 1);
});
