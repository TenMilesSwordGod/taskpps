import json
import shlex
import tempfile
from pathlib import Path


class TestResultCollectorPlugin:
    """## TestResultCollector 测试结果收集器

    在 pipeline 所有测试任务执行完毕后，自动读取每个 task 的控制台日志，
    按正则规则提取 Pass/Fail/Block/Total 等指标，汇总输出为表格。

    通常配置在 pipeline 顶层的 `post.always` 中，无论成功失败都生成报告。

    ### YAML 用法

    **最简用法 — 使用预置模板：**

    ```yaml
    name: my-test-pipeline
    pipelines:
      - name: tests
        tasks:
          - name: unit-test
            command: pytest tests/ --tb=short
          - name: integration
            command: pytest integration/ --tb=short

    post:
      always:
        - name: collect-report
          plugin: test_result_collector
          params:
            template: "pytest"
            output_format: "markdown"
    ```

    **模板基础上追加自定义规则（+/- 语法）：**

    ```yaml
    params:
      template: "pytest"
      rules:
        - warnings                      # 字符串 → 移除模板中 target=warnings 的规则
        - regex: "(\\d+\\.\\d+)% coverage"  # 对象 → 追加新规则
          target: coverage
          match: last
      clean:
        - target: [coverage]
          type: float
      summary:
        rows:
          - label: "平均覆盖率"
            avg_cov: "avg(coverage)"
    ```

    **完全自定义规则（不使用模板）：**

    ```yaml
    params:
      rules:
        - regex: "(\\d+) passed"
          target: passed
          match: last
        - regex: "(\\d+) failed"
          target: failed
          match: last
        - regex: "collected (\\d+)"
          target: total
        - regex: "Report: (https?://[^\\s>]+)"
          target: url
      clean:
        - target: [passed, failed, total]
          type: int
      summary:
        rows:
          - label: "合计"
            passed: sum
            failed: sum
            total: sum
          - label: "通过率"
            rate: "sum(passed) / sum(total) * 100"
    ```

    ### 参数

    | 参数 | 必填 | 默认值 | 说明 |
    |------|------|--------|------|
    | `template` | 否 | — | 预置模板：`pytest` (匹配 console 汇总行) / `robotframework` |
    | `output_format` | 否 | `markdown` | 输出格式：`markdown` / `json` / `html` |
    | `rules` | 否 | — | 提取规则列表；字符串=从模板移除同名规则，对象=追加规则 |
    | `clean` | 否 | — | 数据清洗规则（追加模式），格式 `[{target: [...], type: "int"}]` |
    | `summary` | 否 | — | 汇总行（追加模式），支持 `sum` / `avg` / `min` / `max` / `count` / 表达式 |

    ### rules 字段说明

    | 字段 | 必填 | 说明 |
    |------|------|------|
    | `regex` | 是 | 正则表达式，必须含一个捕获组 `()` |
    | `target` | 是 | 字段名，也是输出表格的列名 |
    | `match` | 否 | 匹配策略：`last`(默认) / `first` / `sum` / `nth:N` |
    | `idx` | 否 | 列顺序，不传则按配置顺序排列 |
    """

    type = "executor"
    version = "1.0.0"
    params_schema = {
        "output_format": {
            "type": "string",
            "required": False,
            "label": "输出格式",
            "enum": ["markdown", "json", "html"],
            "default": "markdown",
        },
        "template": {
            "type": "string",
            "required": False,
            "label": "预置模板",
            "enum": ["pytest", "robotframework"],
        },
        "rules": {
            "type": "list",
            "required": False,
            "label": "提取规则",
        },
        "clean": {
            "type": "list",
            "required": False,
            "label": "数据清洗规则",
        },
        "summary": {
            "type": "object",
            "required": False,
            "label": "汇总行配置",
        },
    }

    def __init__(
        self,
        output_format="markdown",
        template=None,
        rules=None,
        clean=None,
        summary=None,
    ):
        self.output_format = output_format
        self.template = template
        self.rules = rules or []
        self.clean = clean or []
        self.summary = summary or {}

    def build_command(self) -> str:
        script_dir = Path(__file__).resolve().parent
        script_path = script_dir / "test_result_collector.py"

        config = {
            "output_format": self.output_format,
            "template": self.template,
            "rules": self.rules,
            "clean": self.clean,
            "summary": self.summary,
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="trc_config_"
        ) as f:
            json.dump(config, f, ensure_ascii=False)
            config_path = f.name

        return f"python3 {shlex.quote(str(script_path))} {shlex.quote(config_path)}"
