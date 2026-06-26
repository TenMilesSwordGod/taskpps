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
