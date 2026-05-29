# Taskpps Wiki

轻量级、可扩展的任务编排系统，替代 Jenkins 等重量级 CI/CD 工具用于小型项目。

## 快速导航

| 分类 | 文档 |
|:--|:--|
| 🚀 **入门指南** | [快速开始](./Quick-Start) |
| 📝 **配置** | [流水线配置](./Pipeline-Configuration) - [任务类型](./Task-Types) |
| 🔐 **资源管理** | [Agent 与 Credential ID 系统](./Pipeline-Configuration#credential--agent-引用) |
| 🔌 **扩展** | [执行器](./Executors) - [触发器](./Triggers) - [插件系统](./Plugin-System) |
| 🔗 **API** | [API 参考](./API-Reference) |
| 🛠️ **开发** | [架构设计](./Architecture) - [开发指南](./Development) |
| 💻 **CLI** | [CLI 概述](./CLI-Overview) - [CLI 命令](./CLI-Commands) |
| 🚢 **部署** | [生产部署](./Deployment) |

## 项目架构

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

- **YAML 定义流水线** — Config 继承链，子流水线 DAG 拓扑编排
- **多子流水线** — 一个 YAML 文件可定义多个子流水线，支持子流水线间依赖
- **三种任务类型** — Shell 命令 / SSH 远程 / Python invoke 函数
- **条件执行** — `when` 表达式控制任务是否执行
- **失败重试** — `retry` 失败后等待 5 秒自动重试
- **多命令数组** — `commands` 按顺序执行，任一失败则停止
- **ID 引用系统** — Agent 和 Credential 通过 ID 引用，支持 `${credential:id.field}` 语法
- **执行策略** — `sequential` 串行 / `parallel` 并发
- **插件化** — 触发器(Cron)、通知器、执行器均可扩展
- **可观测** — SSE 实时日志流、运行历史、任务状态跟踪
- **API 密钥认证** — 可选中间件保护
- **国际化** — 内建中文 / 英文支持

## 目录结构

```
taskpps/
├── cli/           # Go CLI (ppsctl) — Cobra + Bubble Tea TUI
├── server/        # Python 后端 — FastAPI + SQLModel + aiosqlite
│   ├── taskpps/   #  核心包:api/ db/ domain/ engine/ executors/ ...
│   └── tests/     #  测试套件(目标 100% 覆盖)
├── examples/      # 示例配置 (v2 新格式)
├── scripts/       # 部署脚本
└── wiki/          # 本 wiki
```