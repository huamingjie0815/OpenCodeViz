import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

export function findPythonBinary() {
  for (const candidate of ["python3", "python"]) {
    const probe = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (probe.status === 0) {
      return candidate;
    }
  }
  return null;
}

export function ensurePythonVersion(pythonCmd) {
  const probe = spawnSync(
    pythonCmd,
    ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
    { encoding: "utf8" }
  );
  if (probe.status !== 0) {
    throw new Error(`Failed to inspect Python version using ${pythonCmd}.`);
  }
  const [major, minor] = probe.stdout.trim().split(".").map(Number);
  if (major < 3 || (major === 3 && minor < 12)) {
    throw new Error(`CodeViz requires Python 3.12+, found ${probe.stdout.trim()}.`);
  }
}

export function createVenv(pythonCmd, venvRoot) {
  if (!fs.existsSync(venvRoot)) {
    const result = spawnSync(pythonCmd, ["-m", "venv", "--system-site-packages", venvRoot], { stdio: "inherit" });
    if (result.status !== 0) {
      throw new Error("Failed to create CodeViz virtual environment.");
    }
  }
}

export function ensureSetuptools(pythonPath) {
  const result = spawnSync(pythonPath, ["-m", "ensurepip", "--upgrade"], { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error("Failed to bootstrap pip/setuptools inside the CodeViz virtual environment.");
  }
}

export function installEditablePackage(pythonPath, packageRoot) {
  const args = ["-m", "pip", "install", "--no-build-isolation", "-e", packageRoot];
  const result = spawnSync(pythonPath, args, { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error("Failed to install CodeViz Python package into the managed virtual environment.");
  }
}

export function runPythonCommand(pythonPath, args, extraEnv = {}) {
  return spawnSync(pythonPath, args, {
    stdio: "inherit",
    env: { ...process.env, ...extraEnv },
  });
}

export function getManagedPythonPath(configRoot) {
  return process.platform === "win32"
    ? path.join(configRoot, "venv", "Scripts", "python.exe")
    : path.join(configRoot, "venv", "bin", "python");
}
