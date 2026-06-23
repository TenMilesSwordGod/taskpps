# Webhook 通知系统使用指南

## 概述

taskpps 的通知系统基于 `NotifierPlugin` 接口 + `EventBus` 事件总线。当 pipeline 执行时，系统会发出事件信号，已注册的 notifier 插件收到后将事件推送到外部 URL。

## 架构

```
Pipeline 执行
    │
    ▼
EventBus.emit("run_completed", ...)
    │
    ├──▶ WebhookNotifier.notify() ──POST──▶ 外部 URL
    ├──▶ SlackNotifier.notify()   ──POST──▶ Slack Webhook
    └──▶ 你的自定义 Notifier.notify()
```

## 可用事件

| 事件名 | 触发时机 | 常用 data 字段 |
|--------|----------|----------------|
| `pipeline_started` | pipeline 开始执行 | `pipeline_file`, `run_id` |
| `task_started` | 单个 task 开始 | `task_name`, `run_id` |
| `task_finished` | 单个 task 完成 | `task_name`, `status`, `duration`, `run_id` |
| `run_completed` | 整个 run 完成 | `run_id`, `pipeline_file`, `success` |
| `run_cancelled` | run 被取消 | `run_id`, `reason` |
| `retry_started` | task 重试开始 | `task_name`, `attempt`, `run_id` |
| `retry_finished` | task 重试结束 | `task_name`, `attempt`, `success` |

## 快速开始

### 方式 1：使用内置 WebhookNotifier（推荐）

1. 将 `examples/notifier_webhook.py` 复制到 `plugins/` 目录：

```bash
cp examples/notifier_webhook.py plugins/
```

2. 在 `taskpps.yaml` 中添加配置：

```yaml
notifiers:
  - name: my-webhook
    type: webhook
    config:
      url: https://your-server.com/webhook
      events:
        - run_completed
        - run_cancelled
      timeout: 10
      retry: 3
```

3. 重启 taskpps，插件会自动注册。

### 方式 2：写一个接收端

```bash
# 启动接收端
uvicorn examples.webhook_receiver:app --host 0.0.0.0 --port 9000
```

然后配置 taskpps 指向 `http://localhost:9000/webhook`。

### 方式 3：直接用 EventBus 监听

```python
from taskpps.events.bus import get_event_bus, SIGNAL_RUN_COMPLETED

bus = get_event_bus()

def on_complete(sender, **kwargs):
    print(f"Run completed: {kwargs}")

bus.on(SIGNAL_RUN_COMPLETED, on_complete)
```

## Payload 格式

所有 webhook POST 的 body 都是 JSON：

```json
{
    "event": "run_completed",
    "data": {
        "run_id": "abc-123",
        "pipeline_file": "deploy.yaml",
        "success": true,
        "started_at": "2026-06-23T10:00:00Z",
        "finished_at": "2026-06-23T10:05:30Z"
    }
}
```

## 自定义 Notifier

继承 `NotifierPlugin` 并实现 `notify` 方法：

```python
from taskpps.plugins.base import NotifierPlugin

class MyNotifier(NotifierPlugin):
    @property
    def name(self):
        return "my-notifier"

    def start(self):
        pass

    def stop(self):
        pass

    def notify(self, event, data):
        # 在这里处理事件
        # event: str — 事件名
        # data: dict — 事件数据
        print(f"Got event: {event}")
```

## 文件清单

| 文件 | 用途 |
|------|------|
| `examples/notifier_webhook.py` | Webhook 通知器插件实现 |
| `examples/webhook_receiver.py` | Webhook 接收端（FastAPI） |
| `examples/event_bus_example.py` | EventBus 直接使用示例 |
| `examples/notify-config.yaml` | YAML 配置示例（Slack/飞书/钉钉） |
