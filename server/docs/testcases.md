# 测试用例覆盖分析

## 模块覆盖总览

| 模块 | 文件 | 已测试场景 | 未测试场景 |
|------|------|-----------|-----------|
| config | config.py | 全部主要功能 | 无重大遗漏 |
| db/engine | engine.py | 创建/复用/关闭/重置引擎 | 无 |
| db/repository | repository.py | CRUD + 过滤 + 状态更新 | 无 |
| domain/pipeline | pipeline.py | 任务解析、管道解析、步骤解析 | 无 |
| domain/dag | dag.py | 拓扑排序、执行层级、环检测、依赖查询 | 无 |
| domain/context | context.py | navigate/set/override/env/ExecutionContext | 无 |
| engine/runner | runner.py | 成功/失败/取消/跳过/依赖/异常 | **_execute_steps() 执行流程** |
| events/bus | bus.py | 单例、注册、触发、取消、常量 | 无 |
| executors/base | base.py | 抽象类校验、日志目录创建 | 无 |
| executors/local | local.py | 成功/失败/超时/取消/环境变量 | **危险命令模式检测** |
| executors/ssh | ssh.py | 连接失败/凭证取消/异常 | 无 |
| executors/invoke | invoke.py | 成功/超时/取消/导入错误/装饰器 | 无 |
| loaders/pipeline | pipeline_loader.py | 加载/替换/空文件/遍历保护 | 路径遍历防护 |
| loaders/agent | agent_loader.py | 加载/未找到/yml扩展 | 无 |
| loaders/credential | credential_loader.py | 加载/未找到/yml扩展 | 无 |
| models | run.py, trigger.py | 枚举值、默认值 | 无 |
| plugins | base.py, cron_trigger.py | 抽象类、启动/停止、_run_loop | 无 |
| schemas | run.py, pipeline.py, trigger.py | 所有模型创建与默认值 | 无 |
| services/pipeline | pipeline_service.py | 创建/获取/列表/取消/清理/参数 | **_handle_run_error 回调** |
| services/trigger | trigger_service.py | 创建/列表/删除 | 无 |
| services/plugin | plugin_manager.py | 发现/注册/启动/停止 | 无 |
| api | runs.py, triggers.py, health.py | 全部路由 | 无 |
| middleware | auth.py | **完全未测试** | **APIKeyMiddleware 鉴权** |
| i18n | i18n.py | **完全未测试** | **Translator/t()/set_locale()** |
| main | main.py | lifespan/cli/mark_external_engine | 无 |

---

## 详细未测试场景

### 1. Middleware 鉴权 — `middleware/auth.py`
- `APIKeyMiddleware.dispatch()` 方法
- API Key 缺失时的 401 响应
- API Key 正确时的正常放行
- 健康检查端点跳过鉴权
- OPTIONS 请求跳过鉴权

### 2. 国际化 — `i18n.py`
- `Translator.__init__()` 构造
- `Translator.t()` 翻译方法（含参数替换）
- `get_translator()` 单例获取
- `set_locale()` 区域设置
- `t()` 快捷翻译函数
- locale 为 "en" 时返回原 key

### 3. 引擎步骤执行 — `engine/runner.py:197-237`
- `_execute_steps()` 多步骤循环执行
- 步骤超时按步分配 (`step_timeout = timeout // len(steps)`)
- 步骤失败时的错误处理和日志记录
- 步骤环境变量合并 (`step_env = {**env, **step.env}`)
- 步骤工作目录合并 (`step_cwd = step.cd or task.cwd`)

### 4. 危险命令检测 — `executors/local.py:13-24, 43-44`
- `_DANGEROUS_PATTERNS` 正则表达式
- 检测到危险模式时返回 `exit_code=1`
- 各种危险模式的触发（rm -rf /, fork bomb, shutdown等）

### 5. PipelineService 任务回调错误处理 — `services/pipeline_service.py:81-90`
- `_handle_run_error()` 静态方法
- `asyncio.CancelledError` 处理
- 其他异常的日志记录

### 6. 路径遍历防护 — `loaders/pipeline_loader.py:42-44`
- 通过 `../` 等路径尝试绕过目录限制
- `OSError/ValueError` 异常时的处理

### 7. Config 旧版配置文件路径 — `config.py:55`
- `.taskpps/taskpps.yaml` 不存在时回退到 `taskpps.yaml`
- 但 `test_config_extra.py:test_find_project_root_creates_project` 已覆盖此路径

---

## 已有测试覆盖的关键场景（摘要）

### API 层
- POST /api/runs/ — 创建运行（含参数、文件不存在、循环依赖）
- GET /api/runs/ — 列表运行（含过滤 pipeline/status/limit）
- GET /api/runs/{id} — 获取运行详情（含不存在）
- GET /api/runs/{id}/logs — 获取日志（含 task/tail/follow/SSE/不存在）
- POST /api/runs/{id}/cancel — 取消运行（含不存在）
- DELETE /api/runs/ — 清理运行（force/keep/older_than）
- POST /api/plugins/triggers/ — 创建触发器
- GET /api/plugins/triggers/ — 列表触发器
- DELETE /api/plugins/triggers/{id} — 删除触发器（含不存在）

### 领域层
- DAG 拓扑排序、执行层级、环检测、未知依赖、级联依赖
- 上下文环境变量构建与优先级
- 参数覆盖（options/tasks name index/numeric index）
- dot path 读写

### 执行器层
- LocalExecutor: 正常执行、失败、环境变量、超时、取消
- SSHExecutor: 连接失败、取消、凭证
- InvokeExecutor: 正常执行、无效任务、无效格式、超时、取消、导入错误、装饰器路径

### DB 层
- RunRepository: 创建/获取/列表(含过滤)/更新状态/删除(全部/保留/按时间)
- TaskRunRepository: 创建/获取/列表/更新状态/取消待定/获取运行中/删除
- TriggerRepository: 创建/获取/列表/删除

### 插件层
- 抽象类校验、CronTrigger 启动/停止/名称/类型
- PluginManager: 注册/发现/加载/启动触发器/停止
