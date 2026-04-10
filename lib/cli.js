import path from "node:path";
import { fileURLToPath } from "node:url";

import { getConfigPath, loadConfig, resolveProjectConfig } from "./config.js";
import { runPythonCommand } from "./python.js";
import { runSetup } from "./setup.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const packageRoot = path.resolve(__dirname, "..");

function usage() {
  console.log(`codeviz <command>

Commands:
  setup [--yes] [--provider <name>] [--model <name>] [--api-key <key>] [--base-url <url>] [--default-port <port>] [--no-browser]
  analyze <project>
  reanalyze <project>
  open <project>
  ask <project> <query>
  compare <project> <query> [--from-version <v>] [--to-version <v>]
`);
}

function parseSetupOptions(argv) {
  const options = { yes: false };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--yes") {
      options.yes = true;
    } else if (token === "--no-browser") {
      options.openBrowser = false;
    } else if (token === "--provider") {
      options.provider = argv[index + 1] || "";
      index += 1;
    } else if (token === "--model") {
      options.model = argv[index + 1] || "";
      index += 1;
    } else if (token === "--api-key") {
      options.apiKey = argv[index + 1] || "";
      index += 1;
    } else if (token === "--base-url") {
      options.baseUrl = argv[index + 1] || "";
      index += 1;
    } else if (token === "--default-port") {
      options.defaultPort = argv[index + 1] || "";
      index += 1;
    }
  }
  return options;
}

function applyConfigArgs(command, argv, config) {
  const args = [...argv];
  if (!args.includes("--port") && Number.isFinite(config.defaultPort)) {
    args.push("--port", String(config.defaultPort));
  }
  if (config.openBrowser === false && !args.includes("--no-browser")) {
    args.push("--no-browser");
  }
  return args;
}

export async function main(argv) {
  const [command, ...rest] = argv;
  if (!command || command === "--help" || command === "-h") {
    usage();
    return;
  }

  if (command === "setup") {
    await runSetup(packageRoot, parseSetupOptions(rest));
    return;
  }

  const globalConfig = loadConfig();
  if (!globalConfig.setupComplete) {
    throw new Error(`CodeViz is not configured yet. Run \`codeviz setup\` first.\nExpected config: ${getConfigPath()}`);
  }

  const projectArg = rest[0];
  const projectConfig = projectArg ? resolveProjectConfig(path.resolve(projectArg)) : globalConfig;
  const finalArgs = applyConfigArgs(command, [command, ...rest], projectConfig);
  const extraEnv = {
    CODEVIZ_CONFIG_PATH: getConfigPath(),
    CODEVIZ_PROVIDER: projectConfig.provider || "",
    CODEVIZ_MODEL: projectConfig.model || "",
    CODEVIZ_API_KEY: projectConfig.apiKey || "",
    CODEVIZ_API_KEY_ENV: projectConfig.apiKeyEnv || "",
    CODEVIZ_BASE_URL: projectConfig.baseUrl || "",
  };

  const result = runPythonCommand(projectConfig.pythonPath, ["-m", "codeviz", ...finalArgs], extraEnv);
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
