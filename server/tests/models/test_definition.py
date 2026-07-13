from __future__ import annotations

import json

from taskpps.models.definition import PipelineDefinition


class TestPipelineDefinition:
    def test_create_with_required_fields(self):
        d = PipelineDefinition(project_id="proj001", file_path="deploy.yaml")
        assert d.id is not None
        assert len(d.id) == 12
        assert d.project_id == "proj001"
        assert d.file_path == "deploy.yaml"
        assert d.name == ""
        assert d.content == "{}"
        assert d.raw_content == ""
        assert d.file_hash == ""
        assert d.active is True
        assert d.created_at is not None
        assert d.updated_at is not None

    def test_create_with_all_fields(self):
        d = PipelineDefinition(
            project_id="proj001",
            file_path="folder/deploy.yaml",
            name="deploy",
            content=json.dumps({"name": "deploy", "tasks": [{"name": "step1"}]}),
            raw_content="name: deploy\ntasks:\n  - name: step1\n",
            file_hash="abc12345",
            active=False,
        )
        assert d.name == "deploy"
        assert d.content == '{"name": "deploy", "tasks": [{"name": "step1"}]}'
        assert d.raw_content == "name: deploy\ntasks:\n  - name: step1\n"
        assert d.file_hash == "abc12345"
        assert d.active is False

    def test_unique_ids(self):
        d1 = PipelineDefinition(project_id="p1", file_path="a.yaml")
        d2 = PipelineDefinition(project_id="p1", file_path="b.yaml")
        assert d1.id != d2.id

    def test_default_active_is_true(self):
        d = PipelineDefinition(project_id="p1", file_path="x.yaml")
        assert d.active is True

    def test_default_content_is_empty_json(self):
        d = PipelineDefinition(project_id="p1", file_path="x.yaml")
        assert d.content == "{}"
        json.loads(d.content)  # 验证是合法 JSON
