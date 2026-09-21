from __future__ import annotations

import pytest
import yaml

from taskpps.loaders.pipeline_loader import load_yaml_strict


class TestLoadYamlStrict:
    """v7 (2026-08): 严格 YAML 解析 —— 拒绝显式重复 key，但保留 merge key 语义。"""

    def test_allows_merge_key_with_explicit_override(self):
        """`<<: *anchor` 合并后显式覆盖同名字段是合法 YAML，不能误判为重复。"""
        text = (
            "base: &base\n"
            "  command: echo base\n"
            "  retry: 1\n"
            "tasks:\n"
            "  - <<: *base\n"
            "    name: t1\n"
            "    command: echo override\n"
        )
        data = load_yaml_strict(text)
        assert data["tasks"][0]["command"] == "echo override"
        assert data["tasks"][0]["retry"] == 1
        # 与标准 safe_load 结果一致
        assert data == yaml.safe_load(text)

    def test_rejects_duplicate_explicit_key(self):
        with pytest.raises(yaml.YAMLError):
            load_yaml_strict("name: a\nname: b\n")

    def test_rejects_duplicate_nested_env_key(self):
        text = "name: p\nconfig:\n  env:\n    TOKEN: first\n    TOKEN: second\n"
        with pytest.raises(yaml.YAMLError):
            load_yaml_strict(text)

    def test_normal_document_unchanged(self):
        text = "name: p\ntasks:\n  - name: t1\n    command: echo ok\n"
        assert load_yaml_strict(text) == yaml.safe_load(text)
