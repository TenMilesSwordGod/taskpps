# Taskpps

轻量级、可扩展的任务编排系统，替代 Jenkins 等重量级 CI/CD 工具用于小型项目。

```
┌─────────────┐     REST API     ┌──────────────────┐
│  ppsctl (Go) │ ◄──────────────► │  Backend (Python) │
└─────────────┘                  └──────────────────┘
                                        │
                           ┌─────────────┼─────────────┐
                           │             │             │
                      ┌────┴────┐  ┌─────┴────┐  ┌────┴────┐
                      │ SQLite  │  │ Executors │  │ Plugins │
                      │ (state) │  │ Local/SSH │  │ Cron... │
                      └─────────┘  │ Invoke    │  └─────────┘
                                   └───────────┘
```

## 特性

- **YAML 定义流水线** — 全局默认值 + 任务级覆盖，极简配置
- **三种任务类型** — Shell 命令 / SSH 远程 / Python invoke 函数
- **DAG 依赖编排** — 拓扑排序、并发执行、失败策略（fail/continue）
- **插件化** — 触发器（Cron）、通知器、执行器均可扩展
- **可观测** — SSE 实时日志流、运行历史、任务状态跟踪
- **API 密钥认证** — 可选中间件保护
- **国际化** — 内建中文 / 英文支持

## 快速开始

```bash
# 1. 安装后端
cd server && uv sync

# 2. 安装 CLI
cd cli && go build -o bin/ppsctl main.go

# 3. 初始化项目
ppsctl init

# 4. 在 pipelines/ 中编写 YAML 流水线，启动服务
uv run taskpps-server

# 5. 运行
ppsctl run deploy.yaml TAG=latest
```

## 项目结构

```
taskpps/
├── cli/           # Go CLI (ppsctl) — Cobra + Bubble Tea TUI
├── server/        # Python 后端 — FastAPI + SQLModel + aiosqlite
│   ├── taskpps/   #  核心包：api/ db/ domain/ engine/ executors/ ...
│   └── tests/     #  测试套件（目标 100% 覆盖）
├── examples/      # 示例配置
└── docs/          # (用户项目运行时目录，gitignored)
```

## 开发

```bash
cd server
uv sync --dev
uv run pytest tests/ -v                           # 运行测试
uv run pytest tests/ --cov=taskpps --cov-report=term-missing  # 覆盖率
cd cli && go build -o bin/ppsctl main.go
```

## 详细文档

| 模块 | 文档 |
|:--|:--|
| 架构设计 | `server/docs/arch.md` |
| 流水线配置 | `server/docs/pipeline.md` |
| 任务类型 | `server/docs/tasks.md` |
| API 参考 | `server/docs/api.md` |
| 执行器 | `server/docs/executors.md` |
| 触发器 | `server/docs/triggers.md` |
| 开发指南 | `server/docs/development.md` |
| CLI 概述 | `cli/docs/overview.md` |
| CLI 命令 | `cli/docs/commands.md` |
| TUI 界面 | `cli/docs/tui.md` |
| CLI 配置 | `cli/docs/config.md` |
