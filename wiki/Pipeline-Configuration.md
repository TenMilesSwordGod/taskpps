# 流水线配置

流水线通过 YAML 文件定义，放置在项目 `pipelines/` 目录下。

## v2 新格式（推荐）

支持多子流水线、条件执行、重试等新特性：

```yaml
name: deploy

config:                        # 顶层默认配置
  host: staging-server         # Agent ID
  credential: default-cred     # Credential ID
  env:
    APP_ENV: staging
  timeout: 600
  retry: 1                     # 失败重试次数
  on_failure: fail
  execution_strategy: sequential

pipelines:                     # 子流水线列表
  - name: build
    tasks:
      - name: compile
        command: make build

      - name: migrate
        invoke:
          task: deploy_tasks.migrate_db
        depends_on: [compile]

      - name: restart
        commands:              # 多命令数组
          - supervisorctl stop all
          - supervisorctl start all
        depends_on: [migrate]

  - name: verify               # 第二个子流水线，依赖 build
    depends_on: [build]
    config:
      execution_strategy: parallel
    tasks:
      - name: health-check
        command: curl -sf http://localhost:8000/health
        when: ${env.APP_ENV} == "staging"
```

## v1 旧格式（兼容）

旧格式仍可使用，会自动包装为单子流水线：

```yaml
name: deploy
options:                       # v1 字段名
  host: staging-server
  credential: default-cred
tasks:
  - name: build
    command: make build
```

## Config / Options 字段

| 字段 | 类型 | 默认值 | 说明 |
|:--|:--|:--|:--|
| `host` | string | — | Agent ID（目标主机） |
| `credential` | string | — | Credential ID（认证凭据） |
| `env` | dict | `{}` | 环境变量 |
| `timeout` | int | — | 超时秒数 |
| `retry` | int | `0` | 失败重试次数（间隔 5 秒） |
| `on_failure` | string | `fail` | `fail` 立即停止 / `continue` 继续执行 |
| `execution_strategy` | string | `sequential` | `sequential` 串行 / `parallel` 并发 |

## Task 字段

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `name` | string | 任务名称（必填） |
| `command` | string | Shell 命令（单行） |
| `commands` | list | Shell 命令数组（按顺序执行，与 command 互斥） |
| `invoke` | object | Python invoke 任务 |
| `steps` | list | 多步骤任务 |
| `depends_on` | list | 依赖任务名列表 |
| `when` | string | 条件表达式，如 `${env.APP_ENV} == "production"` |
| `retry` | int | 覆盖顶层 retry |
| `timeout` | int | 覆盖顶层 timeout |
| `on_failure` | string | 覆盖顶层 on_failure |
| `host` | string | 覆盖顶层 host |
| `credential` | string | 覆盖顶层 credential |
| `env` | dict | 任务级环境变量 |

### `when` 条件表达式

```
when: ${env.APP_ENV} == "production"     # 字符串相等
when: ${env.APP_ENV} != "development"    # 字符串不等
when: ${env.COUNT} == "5"               # 数字比较（字符串处理）
```

表达式为 `false` → 任务标记为 **SKIPPED**，不阻塞下游。

### `commands` 数组执行

```yaml
- name: deploy
  commands:
    - echo "step 1"
    - echo "step 2"
    - exit 1              # 失败
    - echo "step 3"       # 不会执行
  retry: 2                # 整个 commands 数组重试
```

执行日志：

```
Step 1/3: echo "step 1"
Step 2/3: echo "step 2"
Step 3/3: exit 1            ← 失败, exit_code=1
[RETRY 1/2] waiting 5s...
Step 1/3: echo "step 1"
...
```

## Config 继承链

配置优先级从高到低：

```
CLI 参数覆盖(params)
  ↓
任务级 config
  ↓
子流水线级 config (覆盖顶层)
  ↓
顶层 config
  ↓
全局配置 taskpps.yaml
  ↓
代码内置默认值
```

子流水线 config 写了就覆盖顶层，没写就继承顶层。

## 变量引用

支持在 YAML 中引用凭据和 Agent 属性：

| 语法 | 示例 | 说明 |
|:--|:--|:--|
| `${credential:<id>.<field>}` | `${credential:prod-cred.password}` | 从凭据取值 |
| `${agent:<id>.<field>}` | `${agent:prod-server.host}` | 从 Agent 取值 |
| `${env.KEY}` | `${env.APP_ENV}` | 环境变量 |
| `${KEY}` | `${TAG}` | 环境变量（兼容旧格式） |

## 子流水线 DAG

通过 `depends_on` 声明子流水线间依赖，系统自动构建 DAG 拓扑排序：

```yaml
pipelines:
  - name: lint              # Level 0
    tasks: [...]
  - name: test              # Level 1 — 依赖 lint
    depends_on: [lint]
    tasks: [...]
  - name: deploy            # Level 2 — 依赖 test
    depends_on: [test]
    tasks: [...]
```

同层子流水线并发执行，环依赖在校验阶段报错。

## 执行策略

| 策略 | 效果 |
|:--|:--|
| `execution_strategy: sequential`（默认） | 子流水线内同层 task 逐一串行执行 |
| `execution_strategy: parallel` | 子流水线内同层 task 并发执行 |

## 失败策略

| 策略 | 效果 |
|:--|:--|
| `on_failure: fail`（默认） | 任务失败 → 终止所有后续未开始任务 |
| `on_failure: continue` | 任务失败 → 不阻塞无依赖的下游任务 |

可在顶层 config / 子流水线 config / task 级分别设置。

## 参数覆盖

运行流水线时可通过 API 的 `params` 字段覆盖配置：

```json
{
  "pipeline": "deploy.yaml",
  "params": {
    "config.host": "prod-server",
    "config.retry": 3,
    "tasks[\"migrate\"].timeout": 600,
    "tasks[\"migrate\"].env.DB_URL": "postgres://..."
  }
}
```

支持 `options.*` / `config.*` 路径和任务名称索引。