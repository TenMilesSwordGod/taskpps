# taskpps Official Plugins

官方插件目录，Server 启动时自动扫描并加载。

## 目录结构

```
official_plugins/
  <plugin_name>/
    plugin.py           # Python class 定义
```

## 插件类型

V1 仅支持 **ExecutorPlugin**——作为 task 类型在 pipeline YAML 中直接使用。

## 通信协议

Python 插件通过 `build_command()` 生成 shell 命令，由 host 路由决定在本地或远程执行。

Go 二进制插件（向后兼容）通过 stdin/stdout JSON-RPC 2.0 与 Server 通信。

### methods

| Method | 方向 | 说明 |
|--------|------|------|
| `describe` | Server→Plugin | 返回插件元数据（name/type/version/help_msg/params_schema），加载时调用一次 |
| `execute` | Server→Plugin | 执行任务，params 对应用户在 YAML 中填的参数 |
| `on_shutdown` | Server→Plugin | 关闭插件 |

### describe 响应（Python 插件）

```json
{
  "name": "echo",
  "type": "executor",
  "version": "1.0.0",
  "help_msg": "Echo 执行器 — 回显消息。...",
  "params_schema": {
    "message": {"type":"string","required":true,"label":"输出消息"}
  }
}
```

### 安全验证

Server 启动插件时设置 `TASKPPS_VERIFY_KEY` 环境变量。Go 二进制插件必须在 describe 响应中回传此 key。Python 插件不涉及。

超时规则:
- describe: 5s 内必须响应，否则 kill
- execute: 300s 内必须响应，否则 kill

## Python 插件开发

### 最小示例

```python
# official_plugins/echo/plugin.py
class EchoPlugin:
    """Echo 执行器 — 回显消息。

    在 pipeline YAML 中使用:
      plugin: echo
      params:
        message: "hello world"
    """
    type = "executor"
    version = "1.0.0"
    params_schema = {
        "message": {"type": "string", "required": True, "label": "输出消息"},
    }

    def __init__(self, message):
        self.message = message

    def build_command(self) -> str:
        import shlex
        return f"echo {shlex.quote(self.message)}"
```

### 规范

| 项 | 来源 |
|----|------|
| `name` | 目录名（`echo`） |
| `type` | class 变量 `"executor"` |
| `version` | class 变量 `"1.0.0"` |
| `help_msg` | class docstring |
| `params_schema` | class 变量 `dict` |
| `__init__(**params)` | YAML `params:` 逐 key 传入 |
| `build_command()`| 返回 shell 命令字符串 |

## 示例

| 插件 | 目录 | 说明 |
|------|------|------|
| echo | `echo/` | 最小 ExecutorPlugin，回显 message |
| hello | `hello/` | ExecutorPlugin，演示 execute + delay + 参数校验 |
| git_plugin | `git/` | Git 操作，支持 clone/checkout/pull + credential |
| collector | `collector/` | 收集 pipeline 所有 task 结果生成测试报告表格 |
| webhook | `webhook/` | Webhook 通知器，支持 Slack/飞书/钉钉/自定义 URL |

## YAML 语法

```yaml
tasks:
  - name: my_task
    plugin: echo          # 目录名 = class 所在目录名
    params:               # 对应 __init__ 的参数
      message: "hello"
    host: my-agent        # 可选，覆盖 pipeline 级 host
```

- `plugin` 值 = 目录名
- `params` 对应 `__init__` 的参数
- `host` 继承链：task → subpipeline → pipeline config，不设则本地执行
- 远程执行时流程与普通 command 一致（ssh/agent），无需额外部署

## convention

- 目录名 = plugin 名
- `help_msg` 必须包含在 pipeline YAML 中的使用示例
- `params_schema` 中 `required=true` 的字段缺失时报错
- `build_command()` 返回的 shell 命令通过 host 路由执行
