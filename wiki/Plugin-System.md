# 插件系统

Taskpps 拥有完整的插件架构，支持扩展触发器、通知器和执行器。

## 插件类型

| 类型 | 基类 | 说明 |
|:--|:--|:--|
| **TriggerPlugin** | `TriggerPlugin` | 流水线触发器（如 Cron、Webhook） |
| **NotifierPlugin** | `NotifierPlugin` | 事件通知器（如 Slack、邮件） |
| **ExecutorPlugin** | `ExecutorPlugin` | 自定义执行器（如 Docker、K8s） |

## 插件目录结构

插件放置在项目根目录下的 `plugins/` 目录：

```
plugins/
├── __init__.py
├── cron_trigger.py      # 内置的 Cron 触发器
└── slack_notifier/      # 包形式的插件
    ├── __init__.py
    └── main.py
```

## 内置插件

### CronTrigger

定时触发器，使用 cron 表达式：

```yaml
# taskpps.yaml
triggers:
  - type: cron
    schedule: "0 3 * * *"  # 每天凌晨 3 点
    pipeline: "daily-backup.yaml"
```

## 开发新插件

### 1. 触发器插件 (TriggerPlugin)

```python
# plugins/git_webhook.py
from taskpps.plugins.base import TriggerPlugin
from typing import Dict, Any

class GitWebhookTrigger(TriggerPlugin):
    def __init__(self, secret: str, pipeline_file: str, callback=None):
        self._secret = secret
        self._pipeline_file = pipeline_file
        self._callback = callback
        self._running = False

    @property
    def name(self) -> str:
        return f"git-webhook:{self._pipeline_file}"

    def get_type(self) -> str:
        return "git-webhook"

    def start(self) -> None:
        self._running = True
        # 启动 webhook 服务器
        pass

    def stop(self) -> None:
        self._running = False
        # 停止 webhook 服务器
        pass
```

### 2. 通知器插件 (NotifierPlugin)

```python
# plugins/slack_notifier.py
from taskpps.plugins.base import NotifierPlugin
from typing import Dict, Any
import requests

class SlackNotifier(NotifierPlugin):
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "slack"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def notify(self, event: str, data: Dict[str, Any]) -> None:
        message = f"[{event}] {data.get('message', '')}"
        requests.post(self._webhook_url, json={"text": message})
```

### 3. 执行器插件 (ExecutorPlugin)

```python
# plugins/docker_executor.py
from taskpps.plugins.base import ExecutorPlugin
from taskpps.executors.base import BaseExecutor, ExecutorResult
import asyncio
from typing import Dict, Optional

class DockerExecutor(ExecutorPlugin, BaseExecutor):
    @property
    def name(self) -> str:
        return "docker"

    def can_handle(self, task_type: str) -> bool:
        return task_type == "docker"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    async def execute(
        self,
        command: str,
        env: Dict[str, str],
        log_path: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> ExecutorResult:
        # 实现 Docker 容器执行逻辑
        return ExecutorResult(exit_code=0, stdout="Done")
```

## 插件自动发现

`PluginManager` 会自动从 `plugins/` 目录加载插件：

1. 扫描 `plugins/` 目录
2. 识别 `*.py` 文件和子包
3. 查找继承自 `BasePlugin` 的类
4. 实例化并注册插件

## 使用插件

### 在配置文件中配置 Cron 触发器

```yaml
# taskpps.yaml
triggers:
  - type: cron
    schedule: "*/15 * * * *"  # 每 15 分钟
    pipeline: "health-check.yaml"
```

## 插件生命周期

1. **发现** - 启动时自动扫描插件目录
2. **实例化** - 无参构造函数创建实例
3. **启动** - 调用 `plugin.start()`
4. **运行** - 插件处理事件/任务
5. **停止** - 服务关闭时调用 `plugin.stop()`

## 插件元数据（推荐）

在插件模块中添加元数据信息：

```python
# plugins/git/__init__.py
__plugin_name__ = "git"
__plugin_version__ = "1.0.0"
__plugin_author__ = "Your Name"
__plugin_description__ = "Git integration with webhook triggers"

from .git_trigger import GitWebhookTrigger
```
