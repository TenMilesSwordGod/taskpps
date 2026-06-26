class HelloPlugin:
    """Hello Executor Plugin — 演示 taskpps ExecutorPlugin 协议。

    在 pipeline YAML 中使用:
      plugin: hello
      params:
        message: "hello world"
        delay: 1   # 可选，模拟耗时操作(秒)
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
