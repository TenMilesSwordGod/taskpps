from __future__ import annotations

import pytest


class TestRunLogs:
    @pytest.mark.asyncio
    async def test_logs_no_task_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService
        import taskpps.config as cfg

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