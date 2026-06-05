# Taskpps

轻量级、可扩展的任务编排系统,替代 Jenkins 等重量级 CI/CD 工具用于小型项目。

```
┌─────────────┐     REST API     ┌──────────────────┐
│  ppsctl (Go) │ ◄──────────────► │  Backend (Python) │
└─────────────┘                  └──────┬───────────┘
                   WebSocket            │
┌──────────────────────┐               │
│  Execution Agent (Go)│◄──────────────┘
│  (远程执行节点)       │
└──────────────────────┘
```

## 特性

- **YAML 定义流水线** — 全局默认值 + 任务级覆盖,极简配置
- **三种任务类型** — Shell 命令 / SSH 远程 / Python invoke 函数
- **Agent 远程执行** — 通过 WebSocket 连接的后台节点执行任务,支持断线重连
- **DAG 依赖编排** — 拓扑排序、并发执行、失败策略(fail/continue)
- **插件化** — 触发器(Cron)、通知器、执行器均可扩展
- **可观测** — SSE 实时日志流、运行历史、任务状态跟踪
- **API 密钥认证** — 可选中间件保护
- **国际化** — 内建中文 / 英文支持

## 快速开始

```bash
# 1. 安装后端
cd server && uv sync

# 2. 安装 CLI
cd cli && go build -o bin/ppsctl .

# 3. 初始化项目
ppsctl init

# 4. 在 pipelines/ 中编写 YAML 流水线,启动服务
uv run taskpps-server

# 5. 运行
ppsctl run deploy.yaml TAG=latest

# 6. (可选)启动远程执行 Agent
cd execution_agent && go build -o bin/taskpps-agent .
./bin/taskpps-agent --server ws://localhost:26521 --agent-id node1
```

## 项目结构

```
taskpps/
├── cli/               # Go CLI (ppsctl) — Cobra + Bubble Tea TUI
├── server/            # Python 后端 — FastAPI + SQLModel + aiosqlite
│   ├── taskpps/       #   核心包:api/ db/ domain/ engine/ executors/ ...
│   └── tests/         #   测试套件(目标 100% 覆盖)
├── execution_agent/   # Go Agent 执行节点 — WebSocket 远程执行
├── agents/            # Agent SSH 主机配置 (YAML)
├── credentials/       # SSH 凭据配置 (YAML)
├── plugins/           # 用户自定义插件
├── pipelines/         # 用户定义流水线 (YAML)
├── tasks/             # 用户任务仓库
├── wiki/              # 项目维基文档
└── examples/          # 示例配置
```

## 开发

```bash
# 后端
cd server
uv sync --dev
uv run pytest tests/ -v
uv run pytest tests/ --cov=taskpps --cov-report=term-missing

# CLI
cd cli && go build -o bin/ppsctl .

# Agent
cd execution_agent && go test ./... -v
```

## 详细文档

| 模块 | 文档 |
|:--|:--|
| 快速开始 | `wiki/Quick-Start.md` |
| 架构设计 | `wiki/Architecture.md` / `server/docs/arch.md` |
| 流水线配置 | `wiki/Pipeline-Configuration.md` / `server/docs/pipeline.md` |
| 任务类型 | `wiki/Task-Types.md` / `server/docs/tasks.md` |
| 执行器 | `wiki/Executors.md` / `server/docs/executors.md` |
| Agent 节点 | `wiki/Agent.md` |
| 插件系统 | `wiki/Plugin-System.md` |
| 触发器 | `wiki/Triggers.md` / `server/docs/triggers.md` |
| API 参考 | `wiki/API-Reference.md` / `server/docs/api.md` |
| 部署 | `wiki/Deployment.md` |
| 开发指南 | `wiki/Development.md` / `server/docs/development.md` |
| CLI 概述 | `wiki/CLI-Overview.md` / `cli/docs/overview.md` |
| CLI 命令 | `wiki/CLI-Commands.md` / `cli/docs/commands.md` |
| CLI 配置 | `wiki/CLI-Configuration.md` / `cli/docs/config.md` |

