"""Issue #79: 验证 task_summary 字段通过 API 正确返回"""
import pytest
from taskpps.schemas.run import RunResponse, RunListResponse


def test_run_response_accepts_task_summary():
    """RunResponse 模型接受 task_summary 字段"""
    data = {
        "id": "test-run-1",
        "pipeline_name": "test-pipeline",
        "status": "success",
        "created_at": "2026-01-01T00:00:00",
        "task_summary": {"success": 3, "failed": 1, "running": 2},
    }
    resp = RunResponse(**data)
    assert resp.task_summary == {"success": 3, "failed": 1, "running": 2}


def test_run_response_defaults_empty_task_summary():
    """task_summary 默认为空字典"""
    data = {
        "id": "test-run-1",
        "pipeline_name": "test-pipeline",
        "status": "success",
        "created_at": "2026-01-01T00:00:00",
    }
    resp = RunResponse(**data)
    assert resp.task_summary == {}


def test_run_list_response_preserves_task_summary():
    """RunListResponse 序列化时保留 task_summary"""
    data = {
        "items": [
            {
                "id": "run-1",
                "pipeline_name": "p1",
                "status": "success",
                "created_at": "2026-01-01T00:00:00",
                "task_summary": {"success": 2, "failed": 1},
            }
        ],
        "total": 1,
    }
    resp = RunListResponse(**data)
    serialized = resp.model_dump()
    assert serialized["items"][0]["task_summary"] == {"success": 2, "failed": 1}


def test_from_orm_with_parsed_params_includes_task_summary():
    """from_orm_with_parsed_params 包含 task_summary"""
    class FakeORM:
        id = "run-1"
        pipeline_name = "p1"
        pipeline_file = "p1.yaml"
        pipeline_id = ""
        pipeline_version = ""
        project_id = None
        status = "success"
        error = None
        params = "{}"
        started_at = None
        finished_at = None
        created_at = "2026-01-01T00:00:00"
        task_summary = {"running": 1, "success": 3}

    obj = FakeORM()
    resp = RunResponse.from_orm_with_parsed_params(obj)
    assert resp.task_summary == {"running": 1, "success": 3}


def test_from_orm_without_task_summary_defaults_empty():
    """ORM 对象没有 task_summary 属性时默认空字典"""
    class FakeORM:
        id = "run-1"
        pipeline_name = "p1"
        pipeline_file = "p1.yaml"
        pipeline_id = ""
        pipeline_version = ""
        project_id = None
        status = "success"
        error = None
        params = "{}"
        started_at = None
        finished_at = None
        created_at = "2026-01-01T00:00:00"

    obj = FakeORM()
    resp = RunResponse.from_orm_with_parsed_params(obj)
    assert resp.task_summary == {}
