# CodeViz

CodeViz 是一个面向本地仓库的代码关系图与项目问答工具。

它会扫描源码和 Markdown 文档，调用 LLM 提取代码实体与关系，把结果写入项目内的 `.codeviz/` 目录，并提供本地 Web 界面和问答入口用于查看分析结果。

## 现在有什么

- 扫描多语言源码并建立实体图
- 抽取 `calls`、`imports`、`extends`、`implements`、`uses`、`defines` 等关系
- 收集 README / 设计文档等 Markdown 内容
- 把每次分析保存为版本化快照
- 启动本地只读 Web 界面查看图数据
- 基于分析结果做项目问答

## 支持的源码类型

当前扫描器会处理这些后缀：

- JavaScript / TypeScript: `.js` `.jsx` `.mjs` `.cjs` `.ts` `.tsx`
- Python: `.py` `.pyi`
- JVM: `.java` `.kt` `.kts` `.scala`
- Systems: `.go` `.rs` `.c` `.cpp` `.cc` `.cxx` `.h` `.hpp`
- Other: `.rb` `.php` `.swift` `.cs` `.sh` `.bash` `.lua` `.dart`

默认跳过这些目录：

- `.codeviz`
- `.git`
- `.venv` `venv`
- `node_modules`
- `dist` `build` `vendor`
- `fixtures`
- `.next` `.nuxt`
- `target` `out`
- `coverage`

同时会读取项目 `.gitignore` 作为补充过滤条件。

## 仓库结构

```text
src/codeviz/
  app.py             CLI 参数解析
  commands.py        CLI 命令分发
  project.py         分析、打开、问答主流程
  analysis.py        LLM 抽取与图数据落盘
  extractor.py       文件级与跨文件关系抽取
  qa_agent.py        项目问答代理
  server.py          本地 HTTP 服务
  storage.py         `.codeviz` 存储层
  web/               内置前端

lib/
  cli.js             npm CLI 包装层
  setup.js           npm setup 逻辑
  python.js          受管 Python 环境启动逻辑

tests/
  pytest 测试
```

## 依赖要求

- Python 3.12+
- Node.js 18+
- 一个可用的 LLM API Key

Python 运行时依赖定义在 [pyproject.toml](/Users/hmj/Desktop/project/show-your-code/pyproject.toml)。

## 安装方式

### 1. 直接作为 Python 包使用

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

如果需要启用 `deepagents` 驱动的问答代理：

```bash
pip install -e '.[runtime]'
```

此时可直接运行：

```bash
python -m codeviz analyze /path/to/project --no-browser
python -m codeviz open /path/to/project --no-browser
python -m codeviz ask /path/to/project "这个服务层负责什么？"
```

### 2. 作为 npm CLI 使用

先安装当前仓库：

```bash
npm install
npm install -g .
```

然后执行全局初始化：

```bash
codeviz setup
```

`codeviz setup` 会：

- 检查本机是否存在 Python 3.12+
- 在 CodeViz 配置目录创建受管虚拟环境
- 以 editable 模式安装当前 Python 包
- 写入全局配置文件

默认全局配置目录：

- macOS / Linux: `~/.config/codeviz/`
- Windows: `%APPDATA%/codeviz/`

可通过 `CODEVIZ_CONFIG_HOME` 覆盖。

## 两套 setup 的区别

这个仓库里同时存在两套 setup 入口：

- `codeviz setup`
  - 来自 npm CLI 包装层
  - 写全局配置
  - 负责准备受管 Python 环境
- `python -m codeviz setup [project]`
  - 来自 Python CLI
  - 写项目内 `<project>/.codeviz/config.json`
  - 仅配置 provider / model / apiKey / baseUrl / port

如果你是正常使用 CLI，优先走 `codeviz setup`。

## 当前可用命令

### `analyze`

启动本地服务，并在后台开始分析。

```bash
codeviz analyze /path/to/project
codeviz analyze /path/to/project --no-browser
codeviz analyze /path/to/project --port 39127
```

当前实现里，`analyze` 走的是“先开服务，再后台分析”的实时模式。

### `reanalyze`

当前实现与 `analyze` 相同，同样会启动本地服务并触发后台分析。

```bash
codeviz reanalyze /path/to/project --no-browser
```

### `open`

打开已有分析结果对应的本地界面。

```bash
codeviz open /path/to/project
```

如果项目还没有任何分析结果，当前代码会直接报错，不会自动补分析。

### `ask`

基于当前项目快照提问。

```bash
codeviz ask /path/to/project "登录流程是怎么实现的？"
```

如果项目尚未分析，`ask` 会先自动触发分析。

### `setup`

Python CLI 版本的交互式项目配置：

```bash
python -m codeviz setup /path/to/project
```

## 配置来源

运行时会按这个顺序取值：

1. 环境变量
2. 项目配置 `<project>/.codeviz/config.json`
3. npm setup 写入的全局配置

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

## `.codeviz/` 目录

每个被分析的项目都会生成：

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

- `versions/<run_id>/` 是一次分析结果的完整快照
- `current.json` 指向当前正在使用的版本
- `meta.json` 记录分析状态、文件数、实体数、边数等
- `events.json` 记录分析过程事件流
- `chat/` 保存问答会话记录

当前实现已经从旧的 `.codeviz/current/` 目录结构迁移到 `versions/ + current.json` 指针结构。

## Web 界面与 API

本地 HTTP 服务绑定到 `127.0.0.1`。默认端口从 `39127` 开始选择，并主动避开：

- `3000`
- `5173`
- `8000`
- `8080`

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

前端能力：

- 图谱浏览
- 节点搜索
- 节点详情查看
- SSE 状态流
- 聊天面板

## 分析流程

1. 扫描仓库源码文件
2. 基于后缀识别语言
3. 收集文件 hash、大小、路径等元信息
4. 调用 LLM 做单文件实体和边提取
5. 对实体做去重
6. 对 unresolved 边做确定性解析
7. 对剩余 unresolved 边做一次 LLM 跨文件补全
8. 收集 Markdown 文档
9. 生成项目摘要
10. 把结果写入版本目录并更新 `current.json`

## 问答模式

问答入口在 [src/codeviz/qa_agent.py](/Users/hmj/Desktop/project/show-your-code/src/codeviz/qa_agent.py)。

当前行为：

- 有 `deepagents` 且有 API Key 时，使用 agent + tools 问答
- 否则回退为“返回检索到的上下文”

问答上下文来源包括：

- 项目摘要
- 命中的代码实体
- 命中的文档片段
- 最近的聊天历史

## 已知限制

- 抽取质量高度依赖模型输出稳定性
- 超过 `50KB` 的源码文件会被跳过
- `reanalyze` 当前没有独立语义，本质与 `analyze` 相同
- npm 包装层 usage 文本里仍保留了 `compare`，但 Python CLI 实际未实现该命令
- 当前前端是内置静态资源，不是独立前端工程

## 开发

安装依赖：

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[runtime]'
```

运行测试：

```bash
pytest
```

如果只是验证基础安装，也可以直接运行：

```bash
python -m codeviz --help
```
