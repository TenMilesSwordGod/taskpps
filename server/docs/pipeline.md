# 流水线配置

流水线通过 YAML 文件定义，放置在项目 `pipelines/` 目录下。

## 基本结构

```yaml
name: deploy                  # 流水线名称（必填）
options:                      # 全局默认值（可选）
  host: staging-server
  credential: default-cred
  env:
    APP_ENV: staging
  timeout: 600
  on_failure: fail
  shell: /bin/bash

tasks:                        # 任务列表（至少一个）
  - name: pull-images
    command: docker pull myapp:${TAG}
  - name: migrate
    command: alembic upgrade head
    depends_on: [pull-images]
```

## Options 继承链

配置项按优先级从高到低覆盖：

```
CLI 参数覆盖（params） ← 最高
  ↓
任务级 options
  ↓
Pipeline 级 options
  ↓
全局配置 taskpps.yaml
  ↓
代码内置默认值         ← 最低
```

## 依赖与 DAG

通过 `depends_on` 声明任务依赖，系统自动构建 DAG 并拓扑排序：

```yaml
tasks:
  - name: lint           # Level 0 — 无依赖
    command: make lint
  - name: test           # Level 1 — 依赖 lint
    command: make test
    depends_on: [lint]
  - name: build          # Level 1 — 依赖 lint（与 test 同层并发）
    command: make build
    depends_on: [lint]
  - name: deploy         # Level 2 — 依赖 test 和 build
    command: make deploy
    depends_on: [test, build]
```

同一 Level 的任务并发执行。环依赖会在校验阶段报错。

## 失败策略

| 策略 | 效果 |
|:--|:--|
| `on_failure: fail`（默认） | 任务失败 → 终止所有后续未开始任务，流水线状态为 `failed` |
| `on_failure: continue` | 任务失败 → 不阻塞无依赖的下游任务，最终状态为 `partial` |

可在 pipeline 级和 task 级分别设置，task 级覆盖 pipeline 级。

## 环境变量

加载优先级（从高到低）：
1. CLI 参数 `params.env.KEY=VAL`
2. task 级 `env`
3. Pipeline 级 `options.env`
4. 全局配置 `taskpps.yaml` 中的 `env`
5. 系统环境变量

YAML 中支持 `${VAR}` 引用，运行时替换为实际值。

## 参数覆盖

运行流水线时可通过 API 的 `params` 字段覆盖任意配置：

```json
{
  "pipeline": "deploy.yaml",
  "params": {
    "options.host": "prod-server",
    "tasks[\"migrate\"].timeout": 600,
    "tasks[\"migrate\"].env.DB_URL": "postgres://..."
  }
}
```

支持点路径和任务名称索引。
