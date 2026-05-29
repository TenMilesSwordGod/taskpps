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

- **YAML 定义流水线** — Config 继承链，子流水线 DAG 拓扑编排
- **多子流水线** — 一个文件定义多个子流水线，支持子流水线间依赖
- **三种任务类型** — Shell 命令 / SSH 远程 / Python invoke 函数
- **条件执行 + 重试** — `when` 表达式控制执行，`retry` 自动重试
- **ID 引用系统** — Agent/Credential 通过 ID 引用，`${credential:id.field}` 语法
- **插件化** — 触发器(Cron)、通知器、执行器均可扩展
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

## 流水线示例（v2 新格式）

```yaml
# pipelines/deploy.yaml
name: deploy

config:
  host: staging-server          # Agent ID
  credential: default-cred      # Credential ID
  env:
    APP_ENV: staging
  timeout: 600
  retry: 1
  execution_strategy: sequential

pipelines:
  - name: build
    tasks:
      - name: compile
        command: make build
      - name: restart
        commands:
          - supervisorctl stop all
          - supervisorctl start all
        depends_on: [compile]

  - name: verify
    depends_on: [build]
    tasks:
      - name: health-check
        command: curl -sf http://localhost:8000/health
        when: ${env.APP_ENV} == "staging"
```

## 项目结构

```
taskpps/
├── cli/           # Go CLI (ppsctl) — Cobra + Bubble Tea TUI
├── server/        # Python 后端 — FastAPI + SQLModel + aiosqlite
│   ├── taskpps/   #  核心包:api/ db/ domain/ engine/ executors/ ...
│   └── tests/     #  测试套件
├── examples/      # 示例配置
└── docs/          # (用户项目运行时目录, gitignored)
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
| 流水线配置 | [wiki/Pipeline-Configuration](./wiki/Pipeline-Configuration) |
| 任务类型 | [wiki/Task-Types](./wiki/Task-Types) |
| 执行器 | [wiki/Executors](./wiki/Executors) |
| 触发器 | [wiki/Triggers](./wiki/Triggers) |
| 开发指南 | [wiki/Development](./wiki/Development) |