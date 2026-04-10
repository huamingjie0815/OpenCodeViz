import path from "node:path";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

import { defaultConfig, ensureConfigRoot, saveConfig } from "./config.js";
import {
  createVenv,
  ensurePythonVersion,
  ensureSetuptools,
  findPythonBinary,
  getManagedPythonPath,
  installEditablePackage,
} from "./python.js";

function normalizeProvider(provider) {
  if (provider === "google") {
    return "google_genai";
  }
  return provider;
}

function defaultApiEnv(provider) {
  if (provider === "anthropic") return "ANTHROPIC_API_KEY";
  if (provider === "google_genai") return "GOOGLE_API_KEY";
  return "OPENAI_API_KEY";
}

export async function runSetup(packageRoot, options = {}) {
  const configRoot = ensureConfigRoot();
  const pythonCmd = findPythonBinary();
  if (!pythonCmd) {
    throw new Error("Python 3.12+ was not found. Install Python first, then rerun `codeviz setup`.");
  }
  ensurePythonVersion(pythonCmd);

  const venvRoot = path.join(configRoot, "venv");
  createVenv(pythonCmd, venvRoot);
  const managedPython = getManagedPythonPath(configRoot);
  ensureSetuptools(managedPython);
  installEditablePackage(managedPython, packageRoot);

  const base = defaultConfig();
  let provider = normalizeProvider(options.provider || "openai");
  let model = options.model || "";
  let apiKey = options.apiKey || "";
  let baseUrl = options.baseUrl || "";
  let openBrowser = options.openBrowser ?? true;
  let defaultPort = options.defaultPort ? Number(options.defaultPort) : base.defaultPort;
  let maxTokens = options.maxTokens ? Number(options.maxTokens) : base.maxTokens;

  if (!options.yes) {
    const rl = readline.createInterface({ input, output });
    const providerAnswer = (await rl.question(`LLM provider (openai/anthropic/google_genai) [${provider}]: `)).trim();
    provider = normalizeProvider(providerAnswer || provider);
    model = (await rl.question(`Model name${model ? ` [${model}]` : " (leave blank to use provider default)"}: `)).trim() || model;
    apiKey = (await rl.question("API key (stored in local CodeViz config): ")).trim() || apiKey;
    baseUrl = (await rl.question(`Base URL${baseUrl ? ` [${baseUrl}]` : " (optional)"}: `)).trim() || baseUrl;
    const openBrowserAnswer = (await rl.question(`Open browser by default? (${openBrowser ? "Y/n" : "y/N"}): `)).trim().toLowerCase();
    if (openBrowserAnswer) {
      openBrowser = openBrowserAnswer !== "n";
    }
    const portAnswer = (await rl.question(`Default port [${defaultPort}]: `)).trim();
    if (portAnswer) {
      defaultPort = Number(portAnswer);
    }
    const maxTokensAnswer = (await rl.question(`Max tokens per LLM response [${maxTokens}]: `)).trim();
    if (maxTokensAnswer) {
      maxTokens = Number(maxTokensAnswer);
    }
    rl.close();
  }

  saveConfig({
    ...base,
    setupComplete: true,
    pythonPath: managedPython,
    provider,
    model,
    apiKey,
    apiKeyEnv: defaultApiEnv(provider),
    baseUrl,
    openBrowser,
    defaultPort,
    maxTokens,
  });

  console.log(`CodeViz setup complete.\nConfig: ${path.join(configRoot, "config.json")}`);
}
