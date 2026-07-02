class CollectorPlugin:
    """## Collector 结果收集器

收集 pipeline 所有 task 执行结果，生成测试报告表格。

### YAML 用法

```yaml
tasks:
  - name: report
    plugin: collector
    params:
      run_id: "${TASKPPS_RUN_ID}"
      output_format: "markdown"
```

### 输出示例

| Name | Status | Duration | Link |
|------|--------|----------|------|
| build | PASS | 2.3s | ... |
| test | FAIL | 1.5s | ... |

### 参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `run_id` | 是 | — | Run ID，通常用 `${TASKPPS_RUN_ID}` |
| `output_format` | 否 | `markdown` | 输出格式：`markdown` / `json` |
"""
    type = "executor"
    version = "1.0.0"
    params_schema = {
        "run_id": {"type": "string", "required": True, "label": "Run ID"},
        "output_format": {"type": "string", "required": False, "label": "输出格式", "enum": ["markdown", "json"], "default": "markdown"},
    }

    def __init__(self, run_id, output_format="markdown"):
        self.run_id = run_id
        self.output_format = output_format

    def build_command(self) -> str:
        import shlex
        return f"python3 /opt/taskpps/official_plugins/collector/collect.py {shlex.quote(self.run_id)} {shlex.quote(self.output_format)}"
