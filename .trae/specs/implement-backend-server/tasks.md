# Tasks

- [x] Task 1: 项目脚手架与依赖配置
  - [x] 1.1 创建 `server/` 目录结构（taskpps 包、models/schemas/api/services/domain/loaders/executors/engine/events/plugins/db 子包）
  - [x] 1.2 创建 `pyproject.toml`，声明依赖（fastapi, uvicorn, sqlmodel, aiosqlite, pydantic, paramiko, invoke, blinker, pyyaml, croniter）和 `taskpps-server` 入口点
  - [x] 1.3 创建 `server/taskpps/__init__.py` 和所有子包的 `__init__.py`
  - [x] 1.4 创建 `server/taskpps/main.py`，初始化 FastAPI 应用，注册路由和生命周期事件

- [x] Task 2: 全局配置加载
  - [x] 2.1 创建 `server/taskpps/config.py`，实现 `Settings` Pydantic 模型（server, executor, env, plugins, triggers 字段）
  - [x] 2.2 实现从 `taskpps.yaml` 加载配置，文件不存在时使用默认值
  - [x] 2.3 实现配置的单例访问（`get_settings()`）

- [x] Task 3: 数据库层（SQLModel + 异步 SQLite）
  - [x] 3.1 创建 `server/taskpps/db/engine.py`，实现异步 SQLite 引擎创建和会话工厂
  - [x] 3.2 创建 `server/taskpps/models/run.py`，定义 PipelineRun 和 TaskRun SQLModel 模型
  - [x] 3.3 创建 `server/taskpps/models/trigger.py`，定义 Trigger SQLModel 模型
  - [x] 3.4 创建 `server/taskpps/db/repository.py`，实现 Repository 模式的异步数据库访问（CRUD 操作）
  - [x] 3.5 实现数据库自动建表（应用启动时 create_all）

- [x] Task 4: Pydantic Schema 定义
  - [x] 4.1 创建 `server/taskpps/schemas/run.py`，定义 CreateRunRequest、RunResponse、TaskRunResponse、RunListResponse
  - [x] 4.2 创建 `server/taskpps/schemas/pipeline.py`，定义 PipelineYAML、TaskYAML、OptionsYAML、InvokeSpec Pydantic 模型
  - [x] 4.3 创建 `server/taskpps/schemas/trigger.py`，定义 CreateTriggerRequest、TriggerResponse

- [x] Task 5: YAML 配置加载器
  - [x] 5.1 创建 `server/taskpps/loaders/pipeline_loader.py`，实现从 pipelines/ 目录加载 YAML 并用 Pydantic 验证
  - [x] 5.2 创建 `server/taskpps/loaders/agent_loader.py`，实现从 agents/ 目录加载 SSH 主机定义
  - [x] 5.3 创建 `server/taskpps/loaders/credential_loader.py`，实现从 credentials/ 目录加载凭据
  - [x] 5.4 实现环境变量替换 `${VAR}` 逻辑

- [x] Task 6: 领域模型与 DAG 解析
  - [x] 6.1 创建 `server/taskpps/domain/pipeline.py`，定义 Pipeline 领域实体（合并后的运行时流水线定义）
  - [x] 6.2 创建 `server/taskpps/domain/task.py`，定义 Task 领域实体
  - [x] 6.3 创建 `server/taskpps/domain/dag.py`，实现 DAG 构建和拓扑排序，包含循环依赖检测
  - [x] 6.4 创建 `server/taskpps/domain/context.py`，定义 ExecutionContext（环境变量合并、参数覆盖）

- [x] Task 7: 参数覆盖系统
  - [x] 7.1 实现点路径解析器（如 `options.host` → 嵌套字典访问）
  - [x] 7.2 实现任务名称索引解析（如 `tasks["migrate"].timeout`）
  - [x] 7.3 实现覆盖参数合并到流水线定义的逻辑
  - [x] 7.4 实现环境变量优先级合并（CLI > task env > pipeline env > global env > system env）

- [x] Task 8: 任务执行器
  - [x] 8.1 创建 `server/taskpps/executors/base.py`，定义 BaseExecutor 抽象基类（execute, cancel 方法）
  - [x] 8.2 创建 `server/taskpps/executors/local.py`，实现 LocalExecutor（asyncio.subprocess 本地命令执行，实时输出捕获）
  - [x] 8.3 创建 `server/taskpps/executors/ssh.py`，实现 SSHExecutor（paramiko SSH 远程执行）
  - [x] 8.4 创建 `server/taskpps/executors/invoke.py`，实现 InvokeExecutor（动态导入 invoke task 并执行）
  - [x] 8.5 实现执行器工厂（根据任务类型创建对应执行器）

- [x] Task 9: 执行引擎
  - [x] 9.1 创建 `server/taskpps/engine/runner.py`，实现 PipelineRunner
  - [x] 9.2 实现线程池提交和任务调度（根据 DAG 层级并行执行）
  - [x] 9.3 实现失败策略处理（fail/continue）
  - [x] 9.4 实现超时控制（asyncio.wait_for）
  - [x] 9.5 实现运行取消逻辑（取消未开始任务，中断运行中任务）
  - [x] 9.6 实现日志实时写入（.taskpps/logs/<pipeline>/<task>/<execution_id>.log）

- [x] Task 10: 事件总线
  - [x] 10.1 创建 `server/taskpps/events/bus.py`，定义事件信号（pipeline_started, task_started, task_finished, run_completed, run_cancelled）
  - [x] 10.2 在执行引擎关键节点发布事件

- [x] Task 11: 插件框架与 Cron 触发器
  - [x] 11.1 创建 `server/taskpps/plugins/base.py`，定义 TriggerPlugin、NotifierPlugin、ExecutorPlugin 抽象接口
  - [x] 11.2 创建 `server/taskpps/plugins/cron_trigger.py`，实现内置 Cron 触发器（使用 croniter）
  - [x] 11.3 实现插件发现和加载（扫描 plugins/ 目录）

- [x] Task 12: 应用服务层
  - [x] 12.1 创建 `server/taskpps/services/pipeline_service.py`，编排流水线运行（加载 YAML → 合并参数 → 创建记录 → 提交执行）
  - [x] 12.2 创建 `server/taskpps/services/trigger_service.py`，管理触发器注册和生命周期
  - [x] 12.3 创建 `server/taskpps/services/plugin_manager.py`，管理插件加载和事件分发

- [x] Task 13: REST API 路由
  - [x] 13.1 创建 `server/taskpps/api/health.py`，实现 GET /api/health
  - [x] 13.2 创建 `server/taskpps/api/runs.py`，实现 POST /api/runs（创建运行）
  - [x] 13.3 实现 GET /api/runs（列表查询，支持 pipeline/status/limit 过滤）
  - [x] 13.4 实现 GET /api/runs/{run_id}（运行详情）
  - [x] 13.5 实现 GET /api/runs/{run_id}/logs（日志查询，支持 task/tail/follow 参数，SSE 流式响应）
  - [x] 13.6 实现 POST /api/runs/{run_id}/cancel（取消运行）
  - [x] 13.7 实现 DELETE /api/runs（清理历史，支持 older_than/keep/force 参数）
  - [x] 13.8 创建 `server/taskpps/api/triggers.py`，实现 POST /api/plugins/triggers（注册触发器）
  - [x] 13.9 在 main.py 中注册所有路由，配置 CORS

- [x] Task 14: 服务启动脚本与集成测试
  - [x] 14.1 创建 `server/taskpps/__main__.py`，实现 `python -m taskpps` 启动方式
  - [x] 14.2 创建示例配置文件（taskpps.yaml, pipelines/deploy.yaml, agents/example.yaml, credentials/example.yaml）
  - [x] 14.3 端到端验证：启动服务 → 创建运行 → 查询状态 → 查看日志 → 取消运行

# Task Dependencies

- Task 1 (脚手架) → 所有后续 Task
- Task 2 (全局配置) → Task 5, Task 9, Task 11, Task 13
- Task 3 (数据库) → Task 12, Task 13
- Task 4 (Schema) → Task 5, Task 12, Task 13
- Task 5 (YAML 加载器) → Task 6, Task 12
- Task 6 (领域模型/DAG) → Task 9
- Task 7 (参数覆盖) → Task 12
- Task 8 (执行器) → Task 9
- Task 9 (执行引擎) → Task 12, Task 13
- Task 10 (事件总线) → Task 11, Task 12
- Task 11 (插件) → Task 12, Task 13
- Task 12 (服务层) → Task 13
- Task 13 (API 路由) → Task 14
- Task 14 (集成测试) 依赖所有前置 Task

可并行的 Task 组：
- Task 2, Task 3, Task 4 可并行
- Task 5, Task 8 可并行（在 Task 4 完成后）
- Task 6, Task 7, Task 10 可并行
- Task 11 在 Task 10 完成后
