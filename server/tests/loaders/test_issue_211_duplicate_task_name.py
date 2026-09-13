# v1 (2026-09): issue #211 — YAML 同名 task 校验。
# 用户报障：yaml 中存在同名 task 时会显示两个，但只有第一个执行、第二个复用第一个的结果。
# 根因：执行器按 task name 索引（ResolvedSubPipeline.get_task_by_name 只返回首个匹配），
# schema 层未拒绝重名，故在此覆盖"文件加载 + API 保存解析"两条用户路径。

from __future__ import annotations

import pytest
from pydantic import ValidationError

from taskpps.loaders.pipeline_loader import PipelineLoader


def _dup_tasks_yaml() -> str:
    return (
        "name: dup_pipe\ntasks:\n  - name: build\n    command: echo first\n  - name: build\n    command: echo second\n"
    )


class TestDuplicateTaskNameValidation:
    def test_parse_dict_rejects_duplicate_top_level_task_names(self):
        loader = PipelineLoader()
        data = {
            "name": "dup_pipe",
            "tasks": [
                {"name": "build", "command": "echo first"},
                {"name": "build", "command": "echo second"},
            ],
        }
        with pytest.raises(ValidationError) as exc:
            loader.parse_dict(data)
        assert "build" in str(exc.value)

    def test_parse_dict_rejects_duplicate_task_names_in_subpipeline(self):
        loader = PipelineLoader()
        data = {
            "name": "dup_pipe",
            "pipelines": [
                {
                    "name": "stage",
                    "tasks": [
                        {"name": "build", "command": "echo first"},
                        {"name": "build", "command": "echo second"},
                    ],
                }
            ],
        }
        with pytest.raises(ValidationError) as exc:
            loader.parse_dict(data)
        assert "build" in str(exc.value)

    def test_load_all_with_files_and_errors_marks_duplicate_file_invalid(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        (pipelines_dir / "dup.yaml").write_text(_dup_tasks_yaml(), encoding="utf-8")
        loader = PipelineLoader(pipelines_dir)

        valid_specs, invalid_items = loader.load_all_with_files_and_errors()

        assert "dup.yaml" not in valid_specs
        item = next(i for i in invalid_items if i["file"] == "dup.yaml")
        assert "build" in item["validation_error"]["message"]

    def test_load_all_with_files_and_errors_accepts_unique_names(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        (pipelines_dir / "ok.yaml").write_text(
            "name: ok_pipe\ntasks:\n  - name: build\n    command: echo 1\n  - name: test\n    command: echo 2\n",
            encoding="utf-8",
        )
        loader = PipelineLoader(pipelines_dir)

        valid_specs, invalid_items = loader.load_all_with_files_and_errors()

        assert "ok.yaml" in valid_specs
        assert invalid_items == []
