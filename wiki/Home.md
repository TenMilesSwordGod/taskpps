# Taskpps Wiki

轻量级、可扩展的任务编排系统，替代 Jenkins 等重量级 CI/CD 工具用于小型项目。

## 快速导航

| 分类 | 文档 |
|:--|:--|
| 🚀 **入门指南** | [快速开始](./Quick-Start) |
| 📝 **配置** | [流水线配置](./Pipeline-Configuration) - [任务类型](./Task-Types) |
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

- **YAML 定义流水线** — 全局默认值 + 任务级覆盖，极简配置
- **三种任务类型** — Shell 命令 / SSH 远程 / Python invoke 函数
- **DAG 依赖编排** — 拓扑排序、并发执行、失败策略(fail/continue)
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
├── examples/      # 示例配置
├── scripts/       # 部署脚本
└── wiki/          # 本 wiki
```
