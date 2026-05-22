# 触发器

触发器使流水线能够按计划自动运行，无需手动调用。

## Cron 触发器

在 `.taskpps/taskpps.yaml` 中配置：

```yaml
triggers:
  - type: cron
    schedule: "0 2 * * *"       # 每天凌晨 2 点
    pipeline: nightly.yaml
    enabled: true

  - type: cron
    schedule: "*/30 * * * *"    # 每 30 分钟
    pipeline: healthcheck.yaml
    enabled: false               # 禁用，不触发执行
```

### 调度语法

标准 5 位 cron 表达式：

```
┌───────── 分钟 (0-59)
│ ┌───────── 小时 (0-23)
│ │ ┌───────── 日 (1-31)
│ │ │ ┌───────── 月 (1-12)
│ │ │ │ ┌───────── 星期 (0-7, 0=7=周日)
│ │ │ │ │
* * * * *
```

支持的运算符：`,`（列举）、`-`（范围）、`*`（所有）、`/`（步进）、`L`（最后）、`W`（工作日）、`#`（第 N 个星期几）。

### 实现机制

`CronTrigger` 在 `PluginManager` 启动时加载，每个触发器在独立守护线程中运行。每秒检查当前时间是否匹配 cron 表达式，匹配时通过 API 内部调用创建流水线运行。

## Webhook 触发器（规划中）

预留了框架能力，后续可按 `plugins/base.py` 的 `TriggerPlugin` 基类实现。

## 管理命令

通过 ppsctl 管理触发器：

```bash
ppsctl trigger list              # 查看所有触发器
ppsctl trigger add cron ...      # 添加触发器
ppsctl trigger delete <id>       # 删除触发器
```

也可通过 API 管理：

```bash
curl -X POST http://127.0.0.1:26521/api/plugins/triggers/ \
  -H "Content-Type: application/json" \
  -d '{"type": "cron", "config": {"schedule": "0 2 * * *"}, "pipeline": "daily.yaml"}'
```
