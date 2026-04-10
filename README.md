# OpenCodeViz

Local-first code graph analysis and project Q&A for real repositories.

`codeviz-ai` is the npm package name used for publishing.
`codeviz` remains the CLI command.

---

## English

### Overview

OpenCodeViz scans source code and Markdown documents, extracts entities and relationships with an LLM-assisted pipeline, stores versioned analysis snapshots in `.codeviz/`, and serves a local web UI for graph exploration and project Q&A.

### Features

- Multi-language repository scanning
- Code graph extraction for entities and relations
- Markdown document ingestion for project context
- Versioned analysis snapshots
- Local web UI for graph browsing
- Project Q&A based on the latest snapshot

### Supported Source Types

- JavaScript / TypeScript: `.js` `.jsx` `.mjs` `.cjs` `.ts` `.tsx`
- Python: `.py` `.pyi`
- JVM languages: `.java` `.kt` `.kts` `.scala`
- Systems languages: `.go` `.rs` `.c` `.cpp` `.cc` `.cxx` `.h` `.hpp`
- Others: `.rb` `.php` `.swift` `.cs` `.sh` `.bash` `.lua` `.dart`

Default ignored directories:

- `.codeviz`
- `.git`
- `.venv` `venv`
- `node_modules`
- `dist` `build` `vendor`
- `fixtures`
- `.next` `.nuxt`
- `target` `out`
- `coverage`

The scanner also respects project `.gitignore` rules.

### Requirements

- Python 3.12+
- Node.js 18+
- An available LLM API key

Python runtime dependencies are defined in [pyproject.toml](/Users/hmj/Desktop/project/show-your-code/pyproject.toml).

### Package Name and CLI Name

- npm package: `codeviz-ai`
- CLI command: `codeviz`

This means installation uses `codeviz-ai`, but all runtime commands still use `codeviz`.

### Installation

#### Option 1: Python package only

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

To enable the `deepagents`-powered Q&A runtime:

```bash
pip install -e '.[runtime]'
```

Then run:

```bash
python -m codeviz analyze /path/to/project --no-browser
python -m codeviz open /path/to/project --no-browser
python -m codeviz ask /path/to/project "What does this service layer do?"
```

#### Option 2: npm CLI install

Install from the published package:

```bash
npm install -g codeviz-ai
```

Or install from the local repository:

```bash
npm install
npm install -g .
```

Then initialize the managed Python runtime:

```bash
codeviz setup
```

`codeviz setup` will:

- Check for Python 3.12+
- Create a managed virtual environment under the global config directory
- Install the Python package in editable mode
- Write the global CLI config

Default global config directory:

- macOS / Linux: `~/.config/codeviz/`
- Windows: `%APPDATA%/codeviz/`

Override with:

- `CODEVIZ_CONFIG_HOME`

### Deployment and Publish

To prepare the npm package for publishing:

```bash
npm install
npm run build:web
```

To publish:

```bash
npm publish
```

If you publish under an npm scope, keep the CLI `bin.codeviz` mapping unchanged.

### Configuration

Runtime config is resolved in this order:

1. Environment variables
2. Project config: `<project>/.codeviz/config.json`
3. Global config written by `codeviz setup`

Common config fields:

- `provider`
- `model`
- `apiKey`
- `apiKeyEnv`
- `baseUrl`
- `port`

Supported environment variables:

- `CODEVIZ_CONFIG_PATH`
- `CODEVIZ_PROVIDER`
- `CODEVIZ_MODEL`
- `CODEVIZ_API_KEY`
- `CODEVIZ_API_KEY_ENV`
- `CODEVIZ_BASE_URL`

Current default model mapping:

- `openai` -> `gpt-4o-mini`
- `anthropic` -> `claude-sonnet-4-20250514`
- `google_genai` -> `gemini-2.0-flash`

Example project config:

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "apiKeyEnv": "OPENAI_API_KEY",
  "baseUrl": "https://api.openai.com/v1",
  "port": 39127
}
```

### Setup Modes

There are two setup entry points:

- `codeviz setup`
  - npm CLI setup
  - writes global config
  - prepares the managed Python environment
- `python -m codeviz setup [project]`
  - Python CLI setup
  - writes `<project>/.codeviz/config.json`
  - configures provider, model, API key, base URL, and port for one project

For normal CLI usage, prefer `codeviz setup`.

### Commands

#### `analyze`

```bash
codeviz analyze /path/to/project
codeviz analyze /path/to/project --no-browser
codeviz analyze /path/to/project --port 39127
```

Starts the local server and runs analysis in the background.

#### `reanalyze`

```bash
codeviz reanalyze /path/to/project --no-browser
```

Currently behaves the same as `analyze`.

#### `open`

```bash
codeviz open /path/to/project
```

Opens the local UI for an existing snapshot.

#### `ask`

```bash
codeviz ask /path/to/project "How is the login flow implemented?"
```

If the project has not been analyzed yet, `ask` triggers analysis first.

### Data Directory

Each analyzed project gets:

```text
.codeviz/
  config.json
  current.json
  versions/
    <run_id>/
      meta.json
      files.json
      entities.json
      edges.json
      documents.json
      events.json
      project_info.json
  chat/
```

Meaning:

- `versions/<run_id>/` is one full analysis snapshot
- `current.json` points to the active snapshot
- `meta.json` stores status and counters
- `events.json` stores analysis events
- `chat/` stores Q&A sessions

### Web UI and API

The local HTTP server binds to `127.0.0.1`.
The default port selection starts at `39127` and avoids common dev ports such as `3000`, `5173`, `8000`, and `8080`.

Main endpoints:

- `/api/status`
- `/api/graph`
- `/api/project-info`
- `/api/versions`
- `/api/events`
- `/api/stream`
- `/api/chat`
- `/api/chat/session`
- `/api/chat/turn/<turn_id>`

### Repository Layout

```text
src/codeviz/
  app.py
  commands.py
  project.py
  analysis.py
  extractor.py
  qa_agent.py
  server.py
  storage.py
  web/

lib/
  cli.js
  setup.js
  python.js

tests/
```

### Development

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[runtime]'
pytest
```

Basic CLI check:

```bash
python -m codeviz --help
```

### Known Limitations

- Extraction quality depends on model quality and consistency
- Source files larger than `50KB` are skipped
- `reanalyze` does not yet have independent semantics
- The web UI is bundled static content, not a separate frontend app

---

## 中文

### 项目介绍

OpenCodeViz 是一个面向真实本地仓库的代码关系图和项目问答工具。

它会扫描源码与 Markdown 文档，通过 LLM 辅助抽取代码实体和关系，把分析结果按版本写入 `.codeviz/`，再通过本地 Web 界面提供图谱浏览和项目问答能力。

### 功能

- 多语言仓库扫描
- 代码实体与关系图抽取
- Markdown 文档收集与索引
- 版本化分析快照
- 本地图谱界面
- 基于快照的项目问答

### 支持的源码类型

- JavaScript / TypeScript: `.js` `.jsx` `.mjs` `.cjs` `.ts` `.tsx`
- Python: `.py` `.pyi`
- JVM 语言: `.java` `.kt` `.kts` `.scala`
- 系统语言: `.go` `.rs` `.c` `.cpp` `.cc` `.cxx` `.h` `.hpp`
- 其他: `.rb` `.php` `.swift` `.cs` `.sh` `.bash` `.lua` `.dart`

默认会跳过这些目录：

- `.codeviz`
- `.git`
- `.venv` `venv`
- `node_modules`
- `dist` `build` `vendor`
- `fixtures`
- `.next` `.nuxt`
- `target` `out`
- `coverage`

同时会额外读取项目 `.gitignore` 规则。

### 依赖要求

- Python 3.12+
- Node.js 18+
- 一个可用的 LLM API Key

Python 运行时依赖定义在 [pyproject.toml](/Users/hmj/Desktop/project/show-your-code/pyproject.toml)。

### 包名与命令名

- npm 包名：`codeviz-ai`
- CLI 命令：`codeviz`

也就是说，安装时使用 `codeviz-ai`，运行时命令仍然是 `codeviz`。

### 安装部署

#### 方式一：只作为 Python 包使用

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

如果要启用基于 `deepagents` 的问答运行时：

```bash
pip install -e '.[runtime]'
```

然后可以直接运行：

```bash
python -m codeviz analyze /path/to/project --no-browser
python -m codeviz open /path/to/project --no-browser
python -m codeviz ask /path/to/project "这个服务层负责什么？"
```

#### 方式二：作为 npm CLI 安装

安装发布后的 npm 包：

```bash
npm install -g codeviz-ai
```

如果是本地仓库安装：

```bash
npm install
npm install -g .
```

然后执行初始化：

```bash
codeviz setup
```

`codeviz setup` 会：

- 检查系统是否有 Python 3.12+
- 在全局配置目录创建受管虚拟环境
- 以 editable 模式安装 Python 包
- 写入全局 CLI 配置

默认全局配置目录：

- macOS / Linux: `~/.config/codeviz/`
- Windows: `%APPDATA%/codeviz/`

可通过 `CODEVIZ_CONFIG_HOME` 覆盖。

#### npm 发布

发布前建议执行：

```bash
npm install
npm run build:web
```

发布命令：

```bash
npm publish
```

如果后续改成带 scope 的 npm 包，也不要改 `bin.codeviz`，这样命令名可以继续保持稳定。

### 配置

运行时配置读取优先级：

1. 环境变量
2. 项目配置 `<project>/.codeviz/config.json`
3. `codeviz setup` 写入的全局配置

常用配置项：

- `provider`
- `model`
- `apiKey`
- `apiKeyEnv`
- `baseUrl`
- `port`

支持的环境变量：

- `CODEVIZ_CONFIG_PATH`
- `CODEVIZ_PROVIDER`
- `CODEVIZ_MODEL`
- `CODEVIZ_API_KEY`
- `CODEVIZ_API_KEY_ENV`
- `CODEVIZ_BASE_URL`

当前默认模型映射：

- `openai` -> `gpt-4o-mini`
- `anthropic` -> `claude-sonnet-4-20250514`
- `google_genai` -> `gemini-2.0-flash`

项目配置示例：

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "apiKeyEnv": "OPENAI_API_KEY",
  "baseUrl": "https://api.openai.com/v1",
  "port": 39127
}
```

### 两套 setup 的区别

- `codeviz setup`
  - npm CLI 入口
  - 写入全局配置
  - 准备受管 Python 环境
- `python -m codeviz setup [project]`
  - Python CLI 入口
  - 写入 `<project>/.codeviz/config.json`
  - 只配置当前项目的 provider、model、API key、base URL、port

正常使用 CLI 时，优先使用 `codeviz setup`。

### 命令

#### `analyze`

```bash
codeviz analyze /path/to/project
codeviz analyze /path/to/project --no-browser
codeviz analyze /path/to/project --port 39127
```

启动本地服务，并在后台开始分析。

#### `reanalyze`

```bash
codeviz reanalyze /path/to/project --no-browser
```

当前行为与 `analyze` 一致。

#### `open`

```bash
codeviz open /path/to/project
```

打开已有分析快照对应的本地界面。

#### `ask`

```bash
codeviz ask /path/to/project "登录流程是怎么实现的？"
```

如果项目尚未分析，`ask` 会先自动触发分析。

### `.codeviz/` 目录结构

```text
.codeviz/
  config.json
  current.json
  versions/
    <run_id>/
      meta.json
      files.json
      entities.json
      edges.json
      documents.json
      events.json
      project_info.json
  chat/
```

含义：

- `versions/<run_id>/` 是一次完整分析快照
- `current.json` 指向当前使用的版本
- `meta.json` 保存状态和统计信息
- `events.json` 保存分析过程事件
- `chat/` 保存问答记录

### Web 界面与 API

本地 HTTP 服务绑定在 `127.0.0.1`。
默认端口从 `39127` 起选，并主动避开 `3000`、`5173`、`8000`、`8080` 等常见开发端口。

主要接口：

- `/api/status`
- `/api/graph`
- `/api/project-info`
- `/api/versions`
- `/api/events`
- `/api/stream`
- `/api/chat`
- `/api/chat/session`
- `/api/chat/turn/<turn_id>`

### 仓库结构

```text
src/codeviz/
  app.py
  commands.py
  project.py
  analysis.py
  extractor.py
  qa_agent.py
  server.py
  storage.py
  web/

lib/
  cli.js
  setup.js
  python.js

tests/
```

### 开发

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[runtime]'
pytest
```

基础命令检查：

```bash
python -m codeviz --help
```

### 已知限制

- 抽取质量依赖模型能力和稳定性
- 大于 `50KB` 的源码文件会被跳过
- `reanalyze` 目前还没有独立语义
- 前端是内置静态资源，不是独立前端工程
