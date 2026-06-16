from __future__ import annotations

import pytest


class TestYieldCompleteLines:
    def test_normal_lines(self):
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\nline2\n")
        assert lines == ["line1", "line2"]
        assert advance == 12

    def test_incomplete_last_line(self):
        """最后一行不完整（无\\n），不应发送"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\nincomplet")
        assert lines == ["line1"]
        assert advance == 6

    def test_no_newline_at_all(self):
        """完全没有换行符，不发送任何行"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("incomplete")
        assert lines == []
        assert advance == 0

    def test_empty_content(self):
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("")
        assert lines == []
        assert advance == 0

    def test_only_newline(self):
        """仅一个换行符，发送空行"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("\n")
        assert lines == [""]
        assert advance == 1

    def test_crlf_line_endings(self):
        """\\r\\n 换行，\\r 被剥离"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\r\nline2\r\n")
        assert lines == ["line1", "line2"]
        assert advance == 14

    def test_embedded_empty_lines(self):
        """保留中间的空行"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\n\nline3\n")
        assert lines == ["line1", "", "line3"]
        assert advance == 13

    def test_multiple_incomplete_reads(self):
        """模拟多次读取：第一次读到不完整行，第二次读到完整"""
        from taskpps.api.runs import _yield_complete_lines

        # 第一次读: "hel" (不完整)
        l1, a1 = _yield_complete_lines("hel")
        assert l1 == []
        assert a1 == 0

        # 第二次读: "hel" + "lo\n" = "hello\n" (完整了)
        l2, a2 = _yield_complete_lines("hello\n")
        assert l2 == ["hello"]
        assert a2 == 6

    def test_carriage_return_midline_preserved(self):
        """行中间的 \\r 不剥离（用于进度条覆盖显示）"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("Progress: 50%\rProgress: 100%\n")
        assert lines == ["Progress: 50%\rProgress: 100%"]
        assert advance == 29


class TestRunLogs:
    @pytest.mark.asyncio
    async def test_logs_no_task_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert len(data["logs"]) >= 1

    @pytest.mark.asyncio
    async def test_logs_with_task_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?task=deploy.step1")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data

    @pytest.mark.asyncio
    async def test_logs_with_task_filter_no_match(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?task=nonexistent.task")
        assert response.status_code == 200
        data = response.json()
        assert data == {"logs": {}}

    @pytest.mark.asyncio
    async def test_logs_with_tail(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?tail=10")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data

    @pytest.mark.asyncio
    async def test_logs_nonexistent_run(self, client):
        response = await client.get("/api/runs/nonexistent/logs")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_logs_with_follow(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?follow=true")
        # SSE response should be 200 with text/event-stream
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


class TestCleanRunsAPI:
    @pytest.mark.asyncio
    async def test_clean_force(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.delete("/api/runs/?force=true")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_runs"] >= 0

    @pytest.mark.asyncio
    async def test_clean_no_params(self, client, db_engine):
        response = await client.delete("/api/runs/")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_runs"] == 0

    @pytest.mark.asyncio
    async def test_clean_older_than(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.delete("/api/runs/?older_than=365")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_clean_keep(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.delete("/api/runs/?keep=100")
        assert response.status_code == 200


class TestCancelRun:
    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, client):
        response = await client.post("/api/runs/nonexistent/cancel")
        assert response.status_code == 404


class TestListRuns:
    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.get("/api/runs/?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0
