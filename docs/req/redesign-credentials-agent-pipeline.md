# Credentials / Agent / Pipeline 系统重新设计 — 需求文档

> 版本: v2.0\
> 日期: 2026-05-29\
> 状态: ✅ 已实现

***

## 一、当前系统现状分析

### 1.1 当前 Credential 系统

**现状：** 每个凭据一个文件

```
credentials/
├── default.yaml        → { password: "changeme" }       ← 文件名 = 凭据名
└── ssh.yaml            → { credentials: [...list...] }  ← 文件名 = 凭据名
```

**加载方式：** `CredentialLoader.load("default")` → 打开 `credentials/default.yaml`

**问题：**

| 问题                       | 说明                                 |
| :----------------------- | :--------------------------------- |
| 一文件一凭据                   | 不能在一个文件中管理多个凭据                     |
| 无 ID 概念                  | 凭据名 = 文件名，不支持 `id` 字段索引            |
| load\_all 返回 `{文件名: 数据}` | 如果 `ssh.yaml` 内有多个凭据，只能通过文件名找整个文件  |
| 无法按 ID 引用                | `${credential:xxx.password}` 语法不支持 |

### 1.2 当前 Agent 系统

**现状：** 每个 agent 一个文件

```
agents/
└── ssh.yaml            → { agents: [...list...] }
```

**加载方式：** `AgentLoader.load("ssh")` → 打开 `agents/ssh.yaml`

**问题：**

| 问题                    | 说明                                              |
| :-------------------- | :---------------------------------------------- |
| 一文件一 agent（假设）        | 现在 `agents/ssh.yaml` 已经有列表结构，但 loader 没有按 ID 查找 |
| 无 ID 概念               | 和 credential 一样的问题                              |
| 无法按 ID 引用属性           | `${agent:test-agent01.description}` 语法不支持       |
| agent → credential 关联 | `credential_id: test-example-cred` 没有自动解析       |

### 1.3 当前 Pipeline 系统

**现状：**

```yaml
# 当前 schema (PipelineYAML)
name: example
options: { host, credential, env, timeout, on_failure }
tasks: [ { name, command, host, credential, depends_on, ... } ]
```

**与目标 YAML 的差异：**

| 功能                   | 当前                 | 目标                                                              |
| :------------------- | :----------------- | :-------------------------------------------------------------- |
| 单流水线                 | ✅ `name` + `tasks` | 需要支持多个子流水线                                                      |
| 子流水线                 | ❌ 不支持              | ✅ `pipelines: [{name, tasks}, ...]`                             |
| 流水线间依赖               | ❌ 不支持              | ✅ `depends_on: [example]`                                       |
| `config` 块           | ❌ 叫 `options`      | ✅ `config:` (语义更好)                                              |
| `commands` 数组        | ❌ 仅 `command` 单字符串 | ✅ `commands: [cmd1, cmd2]`                                      |
| `when` 条件            | ❌ 不支持              | ✅ `when: ${env.APP_ENV} == "development"`                       |
| `retry`              | ❌ 不支持              | ✅ `retry: 3`                                                    |
| `execution_strategy` | ❌ 不支持              | ✅ `sequential` / `parallel`                                     |
| 变量引用                 | 仅 `${VAR}` 环境变量    | ✅ `${credential:id.field}` / `${agent:id.field}` / `${env.KEY}` |

### 1.4 当前变量替换系统

**现状：** `pipeline_loader.py` 中 `substitute_env_vars()` 只支持 `${VAR_NAME}` 匹配环境变量

```python
_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
# 只替换 env dict 和 os.environ 中的值
```

**不支持：**

- `${credential:<id>.<field>}` — 凭据属性引用
- `${agent:<id>.<field>}` — Agent 属性引用
- `${env.KEY}` — 带 `env.` 前缀的变量引用（当前只用裸变量名）

***

## 二、目标设计

### 2.1 Credential 系统

#### 文件格式

凭据按类型分组，一个 YAML 文件管理一个类型的所有凭据：

```yaml
# credentials/ssh.yaml
credentials:
  - id: test-example-cred            # ← 唯一 ID，用于引用
    name: "测试host的SSH凭据"
    description: "测试host 10.98.72.23 的 SSH 凭据"
    type: ssh-username-password      # 认证方式
    username: admin
    password: user@123

  - id: prod-cred
    name: "生产环境SSH凭据"
    description: "生产服务器 SSH 凭据"
    type: ssh-key
    username: deploy
    key_path: /home/deploy/.ssh/id_rsa

# credentials/git.yaml
credentials:
  - id: github-token
    name: "GitHub Token"
    type: token
    token: ghp_xxxxxxxxxxxx
```

#### 加载器设计

```python
class CredentialLoader:
    def load_all(self) -> Dict[str, Credential]:
        """加载所有凭据，返回 {id: Credential对象}"""
    
    def get(self, credential_id: str) -> Optional[Credential]:
        """按 ID 获取单个凭据"""
    
    def get_field(self, credential_id: str, field: str) -> Any:
        """获取凭据的某个字段值"""
```

#### 引用语法

在 pipeline YAML 中使用：

```yaml
env:
  API_SECRET: ${credential:test-example-cred.password}
  SSH_USER: ${credential:test-example-cred.username}
```

### 2.2 Agent 系统

#### 文件格式

Agent 按类型分组：

```yaml
# agents/ssh.yaml
agents:
  - id: test-agent01                   # ← 唯一 ID
    name: "测试host"
    description: "测试host 10.98.72.23"
    type: ssh-username-password
    host: 10.98.72.23
    port: 22
    credential_id: test-example-cred   # ← 引用凭据 ID
    max_parallel: 3

  - id: test-agent02
    name: "测试host 2"
    description: "第二台测试机"
    type: ssh-username-password
    host: 10.98.72.24
    port: 22
    credential_id: test-example-cred
    max_parallel: 3
```

####  加载器设计

```python
class AgentLoader:
    def load_all(self) -> Dict[str, Agent]:
        """加载所有 agent，返回 {id: Agent对象}"""
    
    def get(self, agent_id: str) -> Optional[Agent]:
        """按 ID 获取单个 agent"""
    
    def get_field(self, agent_id: str, field: str) -> Any:
        """获取 agent 的某个字段值"""
    
    def resolve_credential(self, agent: Agent) -> Optional[Credential]:
        """根据 agent.credential_id 解析凭据"""
```

#### 引用语法

```yaml
# 在 pipeline config 中引用 agent
config:
  host: test-agent01        # 直接用 agent ID

# 在 env 中引用 agent 属性
env:
  HOST_DESCRIPTION: ${agent:test-agent01.description}
  HOST_IP: ${agent:test-agent01.host}
```

#### Agent → Credential 关联

Agent 通过 `credential_id` 字段引用凭据。当创建 executor 时：

1. 通过 `host` 字段（值为 agent ID）查找 Agent
2. 通过 Agent 的 `credential_id` 查找 Credential
3. 用 Credential 的认证信息创建 SSH 连接

### 2.3 Pipeline 系统

#### 新的 YAML Schema

```yaml
# pipelines/test1/test.yaml
name: example                            # 文件名标识
config:                                  # ← 原 options，语义更清晰
  host: test-agent01                     # ← Agent ID，不是文件名
  env:
    APP_ENV: development
    API_SECRET: ${credential:test-example-cred.password}
    HOST_DESCRIPTION: ${agent:test-agent01.description}
  timeout: 600
  retry: 3                               # ← 新增：重试次数
  on_failure: fail
  execution_strategy: sequential         # ← 新增：执行策略

pipelines:                               # ← 支持多个子流水线
  - name: example                        # 子流水线名
    tasks:
      - name: build
        command: echo "building..."
      - name: test
        command: echo "running tests..."
        depends_on: [build]
      - name: upload
        command: echo "uploading to artifactory"
        depends_on: [test]

  - name: deploying                      # 第二个子流水线
    config:                              # 子流水线自己的 config（覆盖顶层）
      host: test-agent02
      env:
        APP_ENV: development
      timeout: 300
      on_failure: fail
      execution_strategy: parallel
    depends_on: [example]                # ← 子流水线间依赖
    tasks:
      - name: deploy01
        command: |
          echo "deploying 01..."
          sleep 10
          echo "deploying 01 done"
      - name: deploy02
        when: ${env.APP_ENV} == "development"   # ← 新增：条件执行
        command: echo "deploying 02..."
      - name: deploy03
        commands:                        # ← 新增：多命令数组
          - echo "deploying 03..."
          - echo "API secret: ${env.API_SECRET}"
          - echo "deploying 03 done"
```

#### Schema 层级关系

```
PipelineFile (顶层)
├── name: str                       # 文件描述名
├── config: PipelineConfig          # 顶层默认配置
│   ├── host: str (agent ID)
│   ├── env: dict
│   ├── timeout: int
│   ├── retry: int                  ← 新增
│   ├── on_failure: str
│   └── execution_strategy: str     ← 新增
└── pipelines: List[SubPipeline]    # 子流水线列表
    ├── name: str
    ├── config: PipelineConfig      # 子流水线配置（覆盖顶层）
    ├── depends_on: List[str]       # ← 新增：子流水线间依赖
    └── tasks: List[Task]
        ├── name: str
        ├── command: str (单命令，兼容旧格式)
        ├── commands: List[str]     # ← 新增：多命令
        ├── when: str               # ← 新增：条件表达式
        ├── depends_on: List[str]
        ├── host: str (agent ID)
        ├── credential: str (credential ID)
        ├── env: dict
        ├── timeout: int
        ├── retry: int
        ├── on_failure: str
        └── steps: List[TaskStep]
```

#### 新增功能详细规格

| 功能                              | 详细说明                                                                            |
| :------------------------------ | :------------------------------------------------------------------------------ |
| **子流水线** (`pipelines`)          | 一个 YAML 文件可定义多个子流水线，构建 DAG 按依赖顺序执行                                              |
| **流水线间依赖** (`depends_on`)       | 子流水线 B 依赖子流水线 A 完成后才执行；同层子流水线可并发                                                |
| **条件执行** (`when`)               | 支持 `${env.KEY} == "value"` 和 `${env.KEY} != "value"` 两种表达式；为 false 时跳过该任务但不阻塞下游 |
| **多命令** (`commands`)            | 字符串数组，按顺序依次执行；任何一条失败则任务标记为 FAILED，后续不再执行                                        |
| **重试** (`retry`)                | 任务失败后等待 5 秒再重试，最多重试 `retry` 次；全部失败后任务状态为 FAILED                                 |
| **执行策略** (`execution_strategy`) | `sequential`：子流水线内同层 task 串行逐一执行；`parallel`：子流水线内同层 task 并发执行                   |

#### 子流水线执行流程

```
YAML 解析 → 变量替换 → Schema 验证 → 构建子流水线 DAG → 按 Level 逐层执行

Level 0: [ build ]              ← 无依赖，先执行
Level 1: [ deploy, notify ]     ← 依赖 build，并发执行
Level 2: [ cleanup ]            ← 依赖 deploy 和 notify

每个子流水线内部：
  1. 解析 config（继承 + 覆盖）
  2. 构建 task DAG
  3. 按 Level 执行 task（根据 execution_strategy 决定串行/并发）
  4. 对每个 task 先评估 when 条件，通过才执行
  5. 失败时根据 retry 重试，最终根据 on_failure 决定是否阻塞下游
```

#### `when` 条件表达式规范

```yaml
# 支持的格式
when: ${env.APP_ENV} == "production"     # 字符串相等
when: ${env.APP_ENV} != "development"    # 字符串不等
when: ${env.COUNT} == "5"               # 数字比较（按字符串处理）

# 表达式为 false → 任务标记为 SKIPPED，不阻塞下游
# 表达式为 true  → 正常执行任务
# 没有 when 字段 → 默认执行
```

#### `commands` 数组执行示例

```yaml
- name: deploy
  commands:
    - echo "step 1: build"
    - echo "step 2: push"
    - exit 1              # ← 失败
    - echo "step 3: done" # ← 不会执行
  retry: 2                # 整个 commands 数组重试 2 次
```

执行日志：

```
Step 1/3: echo "step 1: build"
Step 2/3: echo "step 2: push"
Step 3/3: exit 1            ← 失败，exit_code=1
[RETRY 1/2] waiting 5s...
Step 1/3: echo "step 1: build"
...
```

#### config 继承覆盖规则

```
顶层 config { host: A, timeout: 600, retry: 3 }
  └── 子流水线 config { timeout: 300 }
        → 合并结果 { host: A, timeout: 300, retry: 3 }
        
任务级覆盖同层 config（和现有 behavior 一致）
```

### 2.4 变量替换系统

#### 新增语法

| 语法                           | 示例                                         | 含义              |
| :--------------------------- | :----------------------------------------- | :-------------- |
| `${credential:<id>.<field>}` | `${credential:test-example-cred.password}` | 从凭据中取值          |
| `${agent:<id>.<field>}`      | `${agent:test-agent01.description}`        | 从 Agent 中取值     |
| `${env.KEY}`                 | `${env.APP_ENV}`                           | 从环境变量中取值        |
| `${KEY}`                     | `${APP_ENV}`                               | 从环境变量中取值（兼容旧格式） |

#### 替换时机

变量替换应发生在 **流水线加载时**（pipeline\_loader.load），即 YAML 解析后、Schema 验证前。

#### 替换引擎

```python
_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

def resolve_variable(match, context):
    ref = match.group(1)
    
    if ref.startswith("credential:"):
        _, cred_id, field = ref.split(":", 2)
        # 从 credential loader 中查找
        return credential_loader.get_field(cred_id, field)
    
    elif ref.startswith("agent:"):
        _, agent_id, field = ref.split(":", 2)
        # 从 agent loader 中查找
        return agent_loader.get_field(agent_id, field)
    
    elif ref.startswith("env."):
        key = ref[4:]
        return os.environ.get(key, match.group(0))
    
    else:
        return os.environ.get(ref, match.group(0))
```

***

## 三、代码改动范围

### 3.1 需要修改的文件

| 文件                             | 改动说明                                                   | 影响    |
| :----------------------------- | :----------------------------------------------------- | :---- |
| `schemas/pipeline.py`          | 新增 PipelineFile、SubPipeline、PipelineConfig；扩展 TaskYAML | **高** |
| `domain/pipeline.py`           | 新增 ResolvedSubPipeline，适配新 schema                      | **高** |
| `domain/context.py`            | 新增变量引用解析引擎                                             | **高** |
| `loaders/pipeline_loader.py`   | 支持新 schema，集成变量替换                                      | **高** |
| `loaders/credential_loader.py` | 支持多凭据文件 + ID 索引 + get\_field                           | **高** |
| `loaders/agent_loader.py`      | 支持多 agent 文件 + ID 索引 + get\_field + credential 解析      | **高** |
| `executors/__init__.py`        | `create_executor()` 适配新的 agent/credential ID 查找方式      | **高** |
| `engine/runner.py`             | 支持子流水线串行/并行执行、条件执行、重试                                  | **高** |
| `services/pipeline_service.py` | 适配多子流水线的 Run 创建                                        | **中** |
| `config.py`                    | 可能新增 getter 函数                                         | **低** |

### 3.2 已确认的设计决策

| #  | 问题                   | ✅ 决策                                                               |
| :- | :------------------- | :----------------------------------------------------------------- |
| 1  | `when` 条件表达式         | 第一期仅支持简单的 `==` 和 `!=` 比较，如 `when: ${env.APP_ENV} == "development"` |
| 2  | 子流水线间依赖              | 使用和 task 间依赖一致的 DAG 模型，同层子流水线可并发执行                                 |
| 3  | 子流水线 config 覆盖       | 子流水线 config 写了就覆盖顶层，没写就继承顶层                                        |
| 4  | `retry` 重试策略         | 固定 5 秒延迟后重试                                                        |
| 5  | `commands` 数组执行      | 按顺序依次执行，任何一条失败则整个任务标记为 FAILED，后续命令不再执行                             |
| 6  | `execution_strategy` | 控制子流水线内同层 task 的执行方式：`sequential` 串行逐一执行，`parallel` 并发执行           |

***

## 四、兼容性考虑

### 4.1 向后兼容

| 旧功能                    | 兼容策略                                  |
| :--------------------- | :------------------------------------ |
| 旧 `options` 字段         | 同时支持 `options` 和 `config`，`config` 优先 |
| 单流水线（无 `pipelines` 字段） | 自动包装为 `pipelines: [{name, tasks}]`    |
| 旧的 `command` 单字符串      | 保留，与 `commands` 共存                    |
| 旧的 `${VAR}` 变量替换       | 保留，新增语法追加                             |

### 4.2 配置文件迁移

旧格式仍然可用，新项目使用新格式。提供迁移文档。

***

## 五、实现计划（建议顺序）

| 阶段      | 内容                                                         | 依赖         |
| :------ | :--------------------------------------------------------- | :--------- |
| Phase 1 | 重构 CredentialLoader — 支持多凭据 + ID 索引                        | 无          |
| Phase 2 | 重构 AgentLoader — 支持多 agent + ID 索引 + credential 关联         | Phase 1    |
| Phase 3 | 新增变量替换引擎 — `${credential:...}` `${agent:...}` `${env:...}` | Phase 1, 2 |
| Phase 4 | 重构 Pipeline Schema — 支持子流水线、config、新字段                     | Phase 3    |
| Phase 5 | 重构 Runner — 子流水线执行、条件、重试                                   | Phase 4    |
| Phase 6 | 重构 create\_executor — 适配新的 ID 查找                           | Phase 2    |
| Phase 7 | 更新 PipelineService                                         | Phase 5, 6 |

**实施完成日期:** 2026-05-30  
**测试覆盖:** 172 测试用例，~98% 覆盖率  
**涉及文件:** credential_loader.py, agent_loader.py, pipeline_loader.py, parser.py, context.py, runner.py, pipeline_service.py, create_executor.py, executor_factory.py

