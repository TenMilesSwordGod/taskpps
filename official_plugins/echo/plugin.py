class EchoPlugin:
    """## Echo 执行器

    回显消息到标准输出。

    ### YAML 用法

    ```yaml
    tasks:
      - name: say-hello
        plugin: echo
        params:
          message: "hello world"
    ```

    ### 参数

    | 参数 | 必填 | 说明 |
    |------|------|------|
    | `message` | 是 | 输出消息内容 |
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
