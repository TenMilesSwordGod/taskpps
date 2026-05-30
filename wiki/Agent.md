# Taskpps Agent 文档

## 项目简介

Taskpps (Task Pipelines) — 轻量级、可扩展的任务编排系统,用于替代 Jenkins 等重量级 CI/CD 工具在小型项目中的使用。

### 架构概览

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

### 核心特性

- **极简配置** — YAML 定义流水线,全局默认值 + 任务级覆盖
- **可编程任务** — 支持 Python invoke 任务函数,实现复杂逻辑复用
- **轻量无依赖** — 后端仅需 Python 环境,CLI 为单二进制文件
- **动态参数化** — CLI 运行时覆盖流水线配置
- **插件化扩展** — 触发器、通知器、执行器均可通过插件机制集成
- **状态可观测** — 实时日志、运行历史、任务进度查询
- **Agent 连通性检查** — `ppsctl agent check` 并发流式检测所有 Agent 网络可达性，按文件分组展示

## 开发规则

### 通用规则

1. **代码提交规范**
   - 提交前请确保所有测试通过
   - 使用清晰的提交信息,遵循约定式提交格式
   - 每个提交应包含单一功能或修复

2. **代码风格**
   - 后端:遵循 PEP 8 规范
   - CLI:遵循 Go 标准代码风格
   - 所有代码应包含必要的注释

### 后端开发 (Python)

#### 环境设置

```bash
cd server
uv sync --dev
```

#### 运行测试

```bash
cd server
# 运行所有测试
uv run pytest tests/ -v

# 生成覆盖率报告(目标:100% 测试覆盖率)
uv run pytest tests/ --cov=taskpps --cov-report=term-missing
```

#### 启动开发服务器

```bash
cd server
uv run taskpps-server
# 或
uv run python -m taskpps
```

#### 开发规范

- 所有公共 API 应包含类型注解
- 新增功能必须包含对应的单元测试
- 使用 `uv` 管理依赖,更新依赖后同步 `pyproject.toml` 和 `uv.lock`
- SQLite 设置有 `check_same_thread=False`,注意线程安全问题

### CLI 开发 (Go)

#### 环境设置

```bash
cd cli
# 设置 GOROOT(如有需要)
export GOROOT=/usr/lib/go-1.19
export PATH=$GOROOT/bin:$PATH
```

#### 编译和测试

```bash
cd cli
# 编译项目
go build -v ./...

# 运行测试
go test -v ./...
```

#### 开发规范

- **强制要求**:任何 Go 代码修改后,必须先运行测试和编译通过后才能提交
  ```bash
  cd cli
  go build -v ./...  # 确保能正常编译
  go test -v ./...   # 确保所有测试通过
  gofmt -w .         # 确保代码风格一致
  ```
- 使用 `go mod` 管理依赖
- 新增功能应包含对应的单元测试
- TUI 组件使用 Bubble Tea 框架

## 测试规则

### 后端测试

- 所有新增功能必须包含单元测试
- 集成测试应覆盖主要工作流
- 保持测试覆盖率 100%(除非有充分理由)

### CLI 测试

- 命令行工具应有基础功能测试
- TUI 组件测试应验证主要交互行为
- 测试应能在 CI 环境中稳定运行

## Agent 连通性检查

### 概述

`ppsctl agent` 命令组提供 Agent 网络连通性验证功能,支持在部署前快速巡检所有 Agent 状态。

### 架构

```
CLI (Go)                    Server (Python)
───────                     ───────────────
agent check ──POST────►  /api/agents/check-stream (SSE)
                              │
                    asyncio.create_task × N
                    socket.connect 并发
                              │
              ◄── SSE stream ──┘  逐个推送
```

**并发策略**: 服务端用 `asyncio.create_task` + `asyncio.as_completed` 同时发起所有 Agent 的 TCP socket 连接检查,谁先完成先推送,不互相阻塞。

**本地 Agent**: `host` 为 `localhost` / `127.0.0.1` 的 Agent 直接标记 `ready`,不发起网络连接。

**自动降级**: CLI 优先使用流式端点 `/check-stream`,若服务端版本较旧不支持(404),自动降级到批量 `/check` 端点。

### 文件分组

Agent 定义在 `agents/*.yaml` 文件中,检查结果按源文件分组展示:

```
───── agents/staging.yaml ─────
  staging-server    192.168.1.100:22   ✓ connected   45ms
  dev-server        127.0.0.1:22       ✓ ready        0ms
───── agents/prod.yaml ─────
  prod-server       10.0.0.50:22       ✓ connected  120ms
  prod-worker-01    10.0.0.51:22       ✗ timeout     5000ms

Total: 4 agents — 3 connected, 1 failed
```

### 相关文件

| 文件 | 说明 |
|:--|:--|
| `server/taskpps/services/agent_service.py` | AgentService — `check()` / `check_stream()` / `try_connect()` |
| `server/taskpps/api/agents.py` | REST API — `/agents/check` / `/agents/check-stream` / `/agents/try-connect` |
| `server/taskpps/schemas/agent.py` | Pydantic 数据模型 |
| `server/taskpps/loaders/agent_loader.py` | AgentLoader — YAML 加载 + `_source_file` 元数据 |
| `cli/cmd/agent.go` | CLI — `ppsctl agent` 命令 + 流式显示 + 分组表格 |
| `cli/client/client.go` | API 客户端 — `TryConnect()` / `CheckAgentsStream()` |

## Git 工作流程

1. 创建功能分支
2. 开发和测试
3. 提交代码
4. 推送分支并创建 PR
5. 代码审查和合并

## 项目结构

```
taskpps/
├── cli/                 # Go CLI 工具 (ppsctl)
│   ├── go.mod
│   ├── main.go
│   ├── cmd/
│   ├── client/
│   ├── config/
│   ├── models/
│   └── tui/
├── server/              # Python 后端服务
│   ├── pyproject.toml
│   ├── taskpps/
│   └── tests/
├── examples/            # 示例配置文件
├── agent.md             # 本文档
├── .gitignore
└── README.md
```

## 其他注意事项

- 不要在仓库中提交敏感信息(API 密钥、密码等)
- 使用 `examples/` 目录存放示例配置
- 更新文档以反映代码变更
