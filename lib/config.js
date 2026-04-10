import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const APP_NAME = "codeviz";

export function getConfigRoot() {
  if (process.env.CODEVIZ_CONFIG_HOME) {
    return process.env.CODEVIZ_CONFIG_HOME;
  }
  if (process.platform === "win32") {
    const base = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
    return path.join(base, APP_NAME);
  }
  const xdg = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  return path.join(xdg, APP_NAME);
}

export function ensureConfigRoot() {
  const root = getConfigRoot();
  fs.mkdirSync(root, { recursive: true });
  fs.mkdirSync(path.join(root, "logs"), { recursive: true });
  return root;
}

export function getConfigPath() {
  return path.join(getConfigRoot(), "config.json");
}

export function defaultConfig() {
  const root = getConfigRoot();
  return {
    setupComplete: false,
    pythonPath: process.platform === "win32"
      ? path.join(root, "venv", "Scripts", "python.exe")
      : path.join(root, "venv", "bin", "python"),
    provider: "openai",
    model: "",
    apiKey: "",
    apiKeyEnv: "OPENAI_API_KEY",
    baseUrl: "",
    openBrowser: true,
    defaultPort: 39127,
    snapshotPolicy: "git-only",
    maxTokens: 16384
  };
}

export function loadConfig() {
  const file = getConfigPath();
  if (!fs.existsSync(file)) {
    return defaultConfig();
  }
  return { ...defaultConfig(), ...JSON.parse(fs.readFileSync(file, "utf8")) };
}

export function saveConfig(config) {
  const file = getConfigPath();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(config, null, 2)}\n`, "utf8");
}

export function resolveProjectConfig(projectPath) {
  const localConfigPath = path.join(projectPath, ".codeviz", "config.json");
  if (!fs.existsSync(localConfigPath)) {
    return loadConfig();
  }
  return { ...loadConfig(), ...JSON.parse(fs.readFileSync(localConfigPath, "utf8")) };
}
