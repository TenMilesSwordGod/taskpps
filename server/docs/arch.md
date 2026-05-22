# 架构设计

## 整体架构

Taskpps 采用 C/S 架构，前后端通过 REST API 通信：

```
ppsctl (Go CLI)  ──REST API──►  Backend (Python FastAPI)
                                    │
                    ┌───────────────┼────────────────┐
                    │               │                │
               ┌────┴────┐   ┌──────┴──────┐   ┌────┴────┐
               │  SQLite  │   │  Executors   │   │  Plugins │
               │ (state)  │   │ Local/SSH/.. │   │ Cron/... │
               └─────────┘   └─────────────┘   └─────────┘
```

## 核心模块

### 1. 领域层 `domain/`

- **`pipeline.py`** — `ResolvedPipeline` / `ResolvedTask` / `ResolvedStep`：解析 YAML 流水线为领域对象，实现 options 继承链：全局默认 → pipeline 级 → task 级
- **`dag.py`** — `DAG` 类：拓扑排序、执行层级分组、环检测、依赖/被依赖查询
- **`context.py`** — `ExecutionContext`：环境变量合并（系统 → 全局配置 → pipeline options → task env → CLI 参数），点路径参数覆盖

### 2. 执行引擎 `engine/`

- **`runner.py`** — `PipelineRunner`：按 DAG 层级逐层执行，同层任务并发（`asyncio.gather`），处理依赖关系和失败策略，支持取消
- 执行流程：创建 DB 记录 → DAG 校验 → 逐层执行任务 → 更新状态 → 发射事件

### 3. 执行器 `executors/`

三种执行器通过工厂函数 `create_executor()` 统一创建：

| 执行器 | 方式 | 适用场景 |
|:--|:--|:--|
| `LocalExecutor` | `asyncio.create_subprocess_exec` | 本地 Shell 命令 |
| `SSHExecutor` | paramiko | 远程服务器命令 |
| `InvokeExecutor` | `importlib` 动态导入 | Python 函数调用 |

### 4. 加载器 `loaders/`

- **`PipelineLoader`** — 从 `pipelines/` 读取 YAML，支持 `${ENV_VAR}` 替换，路径穿越防护
- **`AgentLoader`** — 加载 SSH 主机配置
- **`CredentialLoader`** — 加载 SSH 凭据（密钥/密码）

### 5. 事件系统 `events/`

基于 blinker 的信号总线 `EventBus`，事件类型：

- `pipeline_started` / `task_started` / `task_finished` / `run_completed` / `run_cancelled`

### 6. 插件系统 `plugins/`

- **基类**：`BasePlugin` / `TriggerPlugin` / `NotifierPlugin` / `ExecutorPlugin`
- **内建**：`CronTrigger` — 在守护线程中按 cron 表达式定时触发流水线
- **管理**：`PluginManager` — 从 `plugins/` 目录发现、注册、启停插件

### 7. 数据库 `db/`

- **引擎**：异步 SQLAlchemy + aiosqlite，SQLite WAL 模式
- **模型**：`PipelineRun`（运行记录）、`TaskRun`（任务执行记录）、`Trigger`（触发器配置）
- **仓库**：`RunRepository` / `TaskRunRepository` / `TriggerRepository` CRUD

### 8. API 层 `api/`

FastAPI 路由，SSE 实时日志流，可选 API 密钥认证

## 数据流

```
CLI/API → PipelineService → DAG校验 → PipelineRunner
                                         │
                              ┌──────────┴──────────┐
                              │   逐层（Level）执行    │
                              │   ┌────────────────┐ │
                              │   │ Level 0: task A │ │
                              │   │ Level 1: B, C   │ │ (并发)
                              │   │ Level 2: D      │ │
                              │   └────────────────┘ │
                              └─────────────────────┘
                                         │
                              EventBus ←─┘ → PluginManager
                                         │
                                    SQLite (持久化)
```
