from __future__ import annotations

from taskpps.models.run import PipelineRun


class TestPipelineRunSnapshot:
    def test_snapshot_content_default_none(self):
        run = PipelineRun(pipeline_name="test")
        assert run.snapshot_content is None

    def test_snapshot_content_set_and_get(self):
        yaml = "name: deploy\ntasks:\n  - name: step1\n    command: echo hello\n"
        run = PipelineRun(pipeline_name="test", snapshot_content=yaml)
        assert run.snapshot_content == yaml
        assert "step1" in run.snapshot_content

    def test_snapshot_content_empty_string(self):
        run = PipelineRun(pipeline_name="test", snapshot_content="")
        assert run.snapshot_content == ""

    def test_snapshot_content_persists_with_other_fields(self):
        run = PipelineRun(
            pipeline_name="deploy",
            pipeline_file="deploy.yaml",
            pipeline_id="deploy",
            pipeline_version="abc12345",
            project_id="proj001",
            snapshot_content="name: deploy\n",
        )
        assert run.snapshot_content == "name: deploy\n"
        assert run.pipeline_name == "deploy"
        assert run.pipeline_file == "deploy.yaml"
