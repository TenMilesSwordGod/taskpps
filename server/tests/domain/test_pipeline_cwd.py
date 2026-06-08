from __future__ import annotations

from taskpps.domain.pipeline import ResolvedPipeline
from taskpps.schemas.pipeline import PipelineConfig, PipelineYAML, SubPipeline, TaskYAML


def _resolve(yaml_dict: dict) -> ResolvedPipeline:
    spec = PipelineYAML(**yaml_dict)
    return ResolvedPipeline.from_yaml(spec, pipeline_file="test.yaml")


def test_cwd_inherits_from_top_config():
    spec = {
        "name": "p",
        "config": {"cwd": "/top"},
        "pipelines": [
            {
                "name": "sub",
                "tasks": [{"name": "t1", "command": "echo"}],
            }
        ],
    }
    p = _resolve(spec)
    assert p.subpipelines[0].config.cwd == "/top"
    assert p.subpipelines[0].tasks[0].cwd == "/top"


def test_cwd_inherits_from_subpipeline_config():
    spec = {
        "name": "p",
        "config": {"cwd": "/top"},
        "pipelines": [
            {
                "name": "sub",
                "config": {"cwd": "/sub"},
                "tasks": [{"name": "t1", "command": "echo"}],
            }
        ],
    }
    p = _resolve(spec)
    assert p.subpipelines[0].config.cwd == "/sub"
    assert p.subpipelines[0].tasks[0].cwd == "/sub"


def test_task_cwd_overrides_all():
    spec = {
        "name": "p",
        "config": {"cwd": "/top"},
        "pipelines": [
            {
                "name": "sub",
                "config": {"cwd": "/sub"},
                "tasks": [{"name": "t1", "command": "echo", "cwd": "/task"}],
            }
        ],
    }
    p = _resolve(spec)
    assert p.subpipelines[0].tasks[0].cwd == "/task"


def test_legacy_options_cwd():
    spec = {
        "name": "p",
        "options": {"cwd": "/opt"},
        "tasks": [{"name": "t1", "command": "echo"}],
    }
    p = _resolve(spec)
    assert p.top_config.cwd == "/opt"
    assert p.subpipelines[0].tasks[0].cwd == "/opt"
