class HelloPlugin:
    """## Hello 执行器

    演示 taskpps ExecutorPlugin 协议，支持延迟模拟。

    ### YAML 用法

    ```yaml
    tasks:
      - name: demo
        plugin: hello
        params:
          message: "hello world"
          delay: 1
    ```

    ### 参数

    | 参数 | 必填 | 默认值 | 说明 |
    |------|------|--------|------|
    | `message` | 是 | — | 输出消息内容 |
    | `delay` | 否 | `0` | 模拟延迟（秒） |
    """

    type = "executor"
    version = "1.0.0"
    params_schema = {
        "message": {"type": "string", "required": True, "label": "输出消息"},
        "delay": {"type": "integer", "required": False, "default": "0", "label": "模拟延迟(秒)"},
    }

    def __init__(self, message, delay=None):
        self.message = message
        self.delay = int(delay) if delay else 0

    def build_command(self) -> str:
        import shlex

        parts = [f"echo {shlex.quote(self.message)}"]
        if self.delay > 0:
            parts.append(f"sleep {self.delay}")
        return " && ".join(parts)
