# Taskpps

Taskpps (Task Pipelines) — 轻量级、可扩展的任务编排系统，用于替代 Jenkins 等重量级 CI/CD 工具在小型项目中的使用。

## 架构

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

## 项目结构

这是一个 monorepo，包含两个独立的子模块：

```
taskpps/
├── cli/                 # Go CLI 工具 (ppsctl)
│   ├── go.mod
│   ├── main.go
│   ├── cmd/
│   ├── client/
│   ├── config/
│   └── models/
├── server/              # Python 后端服务
│   ├── pyproject.toml
│   ├── taskpps/
│   └── tests/
├── examples/            # 示例配置文件
├── .gitignore
└── README.md
```

## 特性

- **极简配置** — YAML 定义流水线，全局默认值 + 任务级覆盖
- **可编程任务** — 支持 Python invoke 任务函数，实现复杂逻辑复用
- **轻量无依赖** — 后端仅需 Python 环境，CLI 为单二进制文件
- **动态参数化** — CLI 运行时覆盖流水线配置
- **插件化扩展** — 触发器、通知器、执行器均可通过插件机制集成
- **状态可观测** — 实时日志、运行历史、任务进度查询

## 快速开始

### 1. 安装后端

```bash
cd server
uv sync
```

### 2. 初始化项目

```bash
mkdir my-project && cd my-project
mkdir -p pipelines tasks agents credentials plugins
```

创建 `taskpps.yaml` 配置文件（参考 `examples/taskpps.yaml`）。

### 3. 定义流水线

在 `pipelines/` 目录创建 YAML 文件：

```yaml
name: deploy
options:
  host: staging-server
  credential: default-cred
  env:
    APP_ENV: staging
  timeout: 600
  on_failure: fail

tasks:
  - name: pull-images
    command: docker pull myapp:${TAG}
  - name: migrate
    invoke:
      task: deploy_tasks.migrate_db
      kwargs:
        target_version: ${MIGRATE_VERSION}
    timeout: 300
  - name: restart
    command: supervisorctl restart all
    depends_on: [migrate]
```

### 4. 启动服务

```bash
cd server
uv run taskpps-server
# 或
uv run python -m taskpps
```

### 5. 运行流水线

```bash
# 使用 API
curl -X POST http://127.0.0.1:26521/api/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline": "deploy.yaml"}'

# 带参数覆盖
curl -X POST http://127.0.0.1:26521/api/runs/ \
  -H "Content-Type: application/json" \
  -d '{"pipeline": "deploy.yaml", "params": {"options.host": "prod-server"}}'
```

## API 端点

| 端点 | 方法 | 功能 |
|:--|:--|:--|
| `/api/health` | GET | 健康检查 |
| `/api/runs` | POST | 创建流水线运行 |
| `/api/runs` | GET | 列表查询 |
| `/api/runs/{run_id}` | GET | 运行详情 |
| `/api/runs/{run_id}/logs` | GET | 日志查询（支持 SSE 流式） |
| `/api/runs/{run_id}/cancel` | POST | 取消运行 |
| `/api/runs` | DELETE | 清理历史 |
| `/api/plugins/triggers` | POST | 注册触发器 |

## 任务类型

### 命令任务

本地或 SSH 远程执行 shell 命令：

```yaml
tasks:
  - name: build
    command: make build
  - name: deploy-remote
    command: systemctl restart myapp
    host: prod-server
```

### Invoke 任务

调用 Python invoke 函数，支持参数传递：

```yaml
tasks:
  - name: migrate
    invoke:
      task: deploy_tasks.migrate_db
      args: ["--verbose"]
      kwargs:
        target_version: "3.0"
```

## 参数覆盖

通过 API 传递 `params` 字段，支持点路径和任务名称索引：

```json
{
  "pipeline": "deploy.yaml",
  "params": {
    "options.host": "prod-server",
    "tasks[\"migrate\"].timeout": 600
  }
}
```

环境变量优先级（从高到低）：
1. CLI 参数覆盖
2. 任务 `env` 定义
3. Pipeline `options.env` 定义
4. 全局配置 `taskpps.yaml` 中的 `env`
5. 系统环境变量

## 失败策略

- `on_failure: fail`（默认）— 任务失败则终止后续未开始的任务
- `on_failure: continue` — 任务失败不影响独立下游任务，流水线最终状态为 partial

## 触发器

在 `taskpps.yaml` 中配置 Cron 触发器：

```yaml
triggers:
  - type: cron
    schedule: "0 2 * * *"
    pipeline: nightly.yaml
```

## 开发

### 后端开发

```bash
cd server
uv sync --dev
uv run pytest tests/ -v
uv run pytest tests/ --cov=taskpps --cov-report=term-missing  # 100% coverage
```

### CLI 开发

```bash
cd cli
go build -o bin/ppsctl main.go
./bin/ppsctl --help
```

## 技术栈

- **后端**: Python 3.10+, FastAPI, SQLModel, aiosqlite, Pydantic, paramiko, invoke, blinker, croniter
- **CLI**: Go 1.19+, Cobra
- **数据库**: SQLite (异步)
- **包管理**: uv (Python), go mod (Go)
