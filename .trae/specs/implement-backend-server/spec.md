# Taskpps 后端服务实现 Spec

## Why

taskpps 项目需要一个轻量级、可扩展的后端服务来编排和执行流水线任务。后端服务是系统的核心，负责流水线的加载、验证、调度、执行和状态管理，通过 REST API 与 Go CLI 通信。

## What Changes

- 创建 Python 后端项目结构（`server/` 目录），使用 FastAPI + SQLModel + Pydantic + invoke 技术栈
- 实现异步 SQLite 数据库层（SQLModel + aiosqlite），存储运行状态和任务执行记录
- 实现 REST API 层，提供流水线运行、查询、取消、日志流、清理等端点
- 实现 YAML 配置热加载（流水线、Agent、凭据），使用 Pydantic 模型验证
- 实现任务执行引擎：本地命令执行、SSH 远程执行（paramiko）、invoke 任务调用
- 实现 DAG 依赖解析，支持任务并行执行和失败策略
- 实现参数覆盖系统，支持点路径和任务名称索引
- 实现实时日志写入与流式读取
- 实现事件总线（blinker），支持插件订阅生命周期事件
- 实现插件框架和内置 Cron 触发器
- 实现全局配置加载（taskpps.yaml）

## Impact

- Affected specs: 后端服务全部功能（阶段 1-3）
- Affected code: 新建 `server/` 目录，包含完整后端实现

## ADDED Requirements

### Requirement: 项目结构与依赖管理

系统 SHALL 在 `server/` 目录下组织后端代码，使用 `pyproject.toml` 管理依赖，支持 `pip install -e .` 开发安装。

#### Scenario: 项目初始化
- **WHEN** 开发者执行 `pip install -e .[dev]`
- **THEN** 安装所有依赖（fastapi, uvicorn, sqlmodel, aiosqlite, pydantic, paramiko, invoke, blinker, pyyaml, croniter）
- **AND** `taskpps-server` 命令可用

### Requirement: 异步 SQLite 数据库

系统 SHALL 使用 SQLModel + aiosqlite 实现异步 SQLite 数据库访问，数据库文件存储在 `.taskpps/state.db`。

#### Scenario: 数据库初始化
- **WHEN** 后端服务首次启动
- **THEN** 自动创建 `.taskpps/state.db` 及所需表结构（runs, task_runs, triggers）

#### Scenario: 数据库操作
- **WHEN** 服务运行期间执行数据库操作
- **THEN** 所有数据库操作通过异步方式执行，不阻塞事件循环

### Requirement: 数据库模型

系统 SHALL 定义以下 SQLModel 模型：

- **PipelineRun**：id(UUID), pipeline_name, status(pending/running/success/failed/cancelled/partial), params(JSON), started_at, finished_at, created_at
- **TaskRun**：id(UUID), run_id(FK), task_name, task_type(command/invoke), status(pending/running/success/failed/skipped/cancelled), exit_code, started_at, finished_at, log_path, created_at
- **Trigger**：id(UUID), type, config(JSON), pipeline_file, enabled, created_at

#### Scenario: 运行记录创建
- **WHEN** 提交流水线运行请求
- **THEN** 创建 PipelineRun 记录（status=pending）和所有 TaskRun 记录（status=pending）

#### Scenario: 状态流转
- **WHEN** 任务开始执行
- **THEN** TaskRun.status 从 pending 变为 running，started_at 记录当前时间
- **WHEN** 任务执行完成
- **THEN** TaskRun.status 变为 success/failed，记录 exit_code 和 finished_at

### Requirement: REST API 端点

系统 SHALL 提供以下 RESTful API 端点，默认监听 `127.0.0.1:26521`：

| 端点 | 方法 | 功能 |
|:--|:--|:--|
| `/api/runs` | POST | 创建流水线运行 |
| `/api/runs` | GET | 列表查询（支持 pipeline, status, limit 参数） |
| `/api/runs/{run_id}` | GET | 运行详情 |
| `/api/runs/{run_id}/logs` | GET | 日志查询（支持 task, tail, follow 参数，流式响应） |
| `/api/runs/{run_id}/cancel` | POST | 取消运行 |
| `/api/runs` | DELETE | 清理历史（支持 older_than, keep 参数） |
| `/api/plugins/triggers` | POST | 注册触发器 |
| `/api/health` | GET | 健康检查 |

#### Scenario: 创建运行
- **WHEN** POST /api/runs 请求包含 pipeline 文件路径和可选的参数覆盖
- **THEN** 加载并验证 YAML，合并覆盖参数，创建运行记录，提交执行引擎
- **AND** 返回 201 和 run_id

#### Scenario: 查询运行列表
- **WHEN** GET /api/runs 请求包含过滤参数
- **THEN** 返回匹配的运行列表，按创建时间倒序

#### Scenario: 流式日志
- **WHEN** GET /api/runs/{run_id}/logs?follow=true
- **THEN** 返回 SSE 流式响应，实时推送新日志内容

#### Scenario: 取消运行
- **WHEN** POST /api/runs/{run_id}/cancel
- **THEN** 将未开始的任务标记为 cancelled，尝试中断运行中的任务

### Requirement: YAML 配置加载与验证

系统 SHALL 支持热加载 YAML 配置文件，每次运行请求时动态读取。

#### Scenario: 流水线 YAML 加载
- **WHEN** 收到运行请求指定 pipeline 文件
- **THEN** 从 `pipelines/` 目录读取 YAML，使用 Pydantic 模型验证结构
- **AND** 验证 name, options, tasks 字段完整性和类型正确性

#### Scenario: Agent YAML 加载
- **WHEN** 任务指定了 host 引用
- **THEN** 从 `agents/` 目录查找对应 YAML 文件，返回 SSH 连接信息

#### Scenario: 凭据 YAML 加载
- **WHEN** 任务指定了 credential 引用
- **THEN** 从 `credentials/` 目录查找对应 YAML 文件，返回认证信息

#### Scenario: 配置文件不存在
- **WHEN** 引用的 YAML 文件不存在
- **THEN** 返回明确的错误信息，不启动运行

### Requirement: 任务执行引擎

系统 SHALL 提供任务执行引擎，支持三种执行器类型，使用全局线程池执行任务。

#### Scenario: 本地命令执行
- **WHEN** 任务类型为 command 且未指定 host
- **THEN** 使用 asyncio.subprocess 在本地执行命令
- **AND** 实时捕获 stdout/stderr 写入日志文件
- **AND** 支持环境变量替换 `${VAR}`

#### Scenario: SSH 远程执行
- **WHEN** 任务类型为 command 且指定了 host
- **THEN** 使用 paramiko 建立 SSH 连接执行命令
- **AND** 实时捕获输出写入日志文件

#### Scenario: Invoke 任务执行
- **WHEN** 任务类型为 invoke
- **THEN** 动态导入 `tasks/` 目录下的 Python 模块
- **AND** 调用指定的 invoke task 函数，传递 args/kwargs
- **AND** 捕获输出写入日志文件

#### Scenario: 超时控制
- **WHEN** 任务执行时间超过 timeout 设定
- **THEN** 强制终止任务进程，标记 TaskRun 为 failed

### Requirement: DAG 依赖解析

系统 SHALL 解析任务间的 depends_on 依赖关系，构建 DAG 并确定执行顺序。

#### Scenario: 依赖解析
- **WHEN** 流水线包含 depends_on 字段的任务
- **THEN** 构建任务依赖图，拓扑排序确定执行层级
- **AND** 同一层级的无依赖任务并行执行

#### Scenario: 循环依赖检测
- **WHEN** 任务依赖关系形成环
- **THEN** 拒绝运行请求，返回循环依赖错误

#### Scenario: 失败策略 - fail
- **WHEN** on_failure=fail 且某任务失败
- **THEN** 取消所有未开始的下游任务，流水线标记为 failed

#### Scenario: 失败策略 - continue
- **WHEN** on_failure=continue 且某任务失败
- **THEN** 继续执行不受影响的下游任务，流水线最终状态为 partial

### Requirement: 参数覆盖系统

系统 SHALL 支持运行时参数覆盖，优先级从高到低：CLI 覆盖 > 任务 env > Pipeline options.env > 全局配置 env > 系统环境变量。

#### Scenario: 点路径覆盖
- **WHEN** 覆盖参数为 `{"options.host": "prod-server"}`
- **THEN** 将流水线 options.host 替换为 prod-server

#### Scenario: 任务名称索引覆盖
- **WHEN** 覆盖参数为 `{"tasks[\"migrate\"].timeout": 300}`
- **THEN** 将名为 migrate 的任务 timeout 替换为 300

#### Scenario: 环境变量合并
- **WHEN** 多层 env 定义存在相同键
- **THEN** 按优先级高者覆盖低者

### Requirement: 日志系统

系统 SHALL 将任务执行日志写入 `.taskpps/logs/<pipeline>/<task>/<execution_id>.log`，支持实时写入和流式读取。

#### Scenario: 日志写入
- **WHEN** 任务执行产生输出
- **THEN** 实时追加写入对应日志文件

#### Scenario: 日志查询
- **WHEN** GET /api/runs/{run_id}/logs?task=pull-images&tail=100
- **THEN** 返回指定任务最后 100 行日志

#### Scenario: 日志流式跟随
- **WHEN** GET /api/runs/{run_id}/logs?follow=true
- **THEN** 返回 SSE 流，持续推送新日志直到任务完成

### Requirement: 事件总线

系统 SHALL 使用 blinker 实现事件总线，发布生命周期事件供插件订阅。

#### Scenario: 事件发布
- **WHEN** 流水线启动、任务完成、运行取消等事件发生
- **THEN** 发布对应信号（pipeline_started, task_finished, run_cancelled 等）

#### Scenario: 事件订阅
- **WHEN** 插件注册了事件处理器
- **THEN** 对应事件发生时自动调用处理器

### Requirement: 插件框架

系统 SHALL 提供插件框架，定义标准接口，支持从 plugins/ 目录发现和加载插件。

#### Scenario: 插件加载
- **WHEN** 服务启动
- **THEN** 扫描 plugins/ 目录和配置的插件路径，加载符合接口的插件

#### Scenario: 触发器插件
- **WHEN** 注册 Cron 触发器
- **THEN** 按 cron 表达式定时触发流水线运行

### Requirement: 全局配置加载

系统 SHALL 从 `taskpps.yaml` 加载全局配置，包括服务器地址、执行器参数、环境变量等。

#### Scenario: 配置加载
- **WHEN** 服务启动
- **THEN** 读取 taskpps.yaml，配置服务器监听地址和端口、线程池大小、默认超时等

#### Scenario: 配置缺失
- **WHEN** taskpps.yaml 不存在
- **THEN** 使用内置默认值（host=127.0.0.1, port=26521, max_workers=10, default_timeout=3600）

### Requirement: 清理与维护 API

系统 SHALL 提供清理历史数据的 API。

#### Scenario: 按时间清理日志
- **WHEN** DELETE /api/runs?older_than=7d
- **THEN** 删除 7 天前的运行记录及关联日志文件

#### Scenario: 保留最近记录
- **WHEN** DELETE /api/runs?keep=100
- **THEN** 保留最近 100 条记录，删除其余记录及日志

#### Scenario: 全量清理
- **WHEN** DELETE /api/runs?force=true
- **THEN** 清空所有运行记录和日志文件

## MODIFIED Requirements

无（初始实现）

## REMOVED Requirements

无（初始实现）
