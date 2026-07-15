# v1 (2026-07): issue #195 — PipelineLoader.load_all_with_files_and_errors 的校验测试
# 覆盖：合法 YAML 正确归类 / YAML 语法错误纳入 invalid / 空文件纳入 invalid / pydantic 校验错误纳入 invalid

from __future__ import annotations

import pytest

from taskpps.loaders.pipeline_loader import PipelineLoader


class TestLoadAllWithFilesAndErrors:
    @pytest.mark.zentao("TC-S1001", domain="server/loaders", priority="P1")
    def test_invalid_yaml_syntax_error_to_invalid_list(self, tmp_path):
        """TC-S1001: 非法YAML语法错误 → 出现在 invalid_items 中，含 validation_error"""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        bad_yaml = pipelines_dir / "bad_syntax.yaml"
        bad_yaml.write_text("name: bad\n  tasks:    \n  - name: broken\n   indent: wrong\n")
        loader = PipelineLoader(pipelines_dir)
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert "bad_syntax" not in valid_specs
        assert len(invalid_items) >= 1
        bad_item = [i for i in invalid_items if i["file"] == "bad_syntax.yaml"][0]
        assert bad_item["name"] == "bad_syntax"
        assert "validation_error" in bad_item
        assert bad_item["validation_error"] is not None
        assert "message" in bad_item["validation_error"]
        assert isinstance(bad_item["validation_error"]["message"], str)
        assert len(bad_item["validation_error"]["message"]) > 0

    @pytest.mark.zentao("TC-S1001", domain="server/loaders", priority="P1")
    def test_empty_yaml_file_to_invalid_list(self, tmp_path):
        """空YAML文件 → 出现在 invalid_items 中，validation_error.line=1, column=1"""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        empty_yaml = pipelines_dir / "empty_file.yaml"
        empty_yaml.write_text("")
        loader = PipelineLoader(pipelines_dir)
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert "empty_file" not in valid_specs
        assert len(invalid_items) >= 1
        empty_item = [i for i in invalid_items if i["file"] == "empty_file.yaml"][0]
        assert empty_item["validation_error"]["line"] == 1
        assert empty_item["validation_error"]["column"] == 1

    @pytest.mark.zentao("TC-S1001", domain="server/loaders", priority="P1")
    def test_invalid_schema_to_invalid_list_with_path(self, tmp_path):
        """语法合法但缺必填字段（如缺name）→ invalid_items，validation_error 含 path"""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        no_name_yaml = pipelines_dir / "no_name.yaml"
        no_name_yaml.write_text("tasks:\n  - name: step1\n    command: echo hello\n")
        loader = PipelineLoader(pipelines_dir)
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert "no_name" not in valid_specs
        invalid_no_name = [i for i in invalid_items if i["file"] == "no_name.yaml"][0]
        assert invalid_no_name["validation_error"] is not None
        assert "message" in invalid_no_name["validation_error"]
        # pydantic 校验应包含 path 字段
        assert invalid_no_name["validation_error"].get("path") is not None

    @pytest.mark.zentao("TC-S1002", domain="server/loaders", priority="P1")
    def test_valid_yaml_to_valid_dict(self, tmp_path):
        """TC-S1002: 合法 YAML pipeline 出现在 valid dict 中"""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        valid_yaml = pipelines_dir / "my_pipe.yaml"
        valid_yaml.write_text("name: my_pipe\ntasks:\n  - name: step1\n    command: echo ok\n")
        loader = PipelineLoader(pipelines_dir)
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert "my_pipe.yaml" in valid_specs
        assert valid_specs["my_pipe.yaml"].name == "my_pipe"
        assert len(invalid_items) == 0

    @pytest.mark.zentao("TC-S1001", domain="server/loaders", priority="P2")
    def test_valid_and_invalid_mixed(self, tmp_path):
        """合法与非法YAML文件混合时，valid 只含合法，invalid 只含非法"""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        # 合法文件
        (pipelines_dir / "ok.yaml").write_text("name: ok\n")
        # 非法文件
        (pipelines_dir / "bad.yaml").write_text(
            "name: bad\ntasks: not_an_array\noptions:\n  on_failure: fail\n"
        )
        loader = PipelineLoader(pipelines_dir)
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert "ok.yaml" in valid_specs
        assert "bad.yaml" not in valid_specs
        bad_files = [i["file"] for i in invalid_items]
        assert "bad.yaml" in bad_files
        # 合法的不在 invalid 中
        assert "ok.yaml" not in bad_files

    @pytest.mark.zentao("TC-S1001", domain="server/loaders", priority="P2")
    def test_bad_task_type_to_invalid_list(self, tmp_path):
        """tasks 字段类型错误（非数组）→ invalid_items"""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        bad_tasks_yaml = pipelines_dir / "bad_tasks_type.yaml"
        bad_tasks_yaml.write_text("name: bad_tasks\ntasks: not_an_array\n")
        loader = PipelineLoader(pipelines_dir)
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert "bad_tasks" not in valid_specs
        assert len(invalid_items) >= 1

    @pytest.mark.zentao("TC-S1001", domain="server/loaders", priority="P2")
    def test_no_directory_returns_empty(self, tmp_path):
        """base_dir 不存在时返回空"""
        loader = PipelineLoader(tmp_path / "nonexistent")
        valid_specs, invalid_items = loader.load_all_with_files_and_errors()
        assert valid_specs == {}
        assert invalid_items == []
