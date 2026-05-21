import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from taskpps.main import app


@pytest.mark.asyncio
async def test_get_run_logs_run_not_found(client, setup_project, tmp_project):
    response = await client.get("/api/runs/nonexistent/logs")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_logs_follow(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(1)
    response = await client.get(f"/api/runs/{run_id}/logs?follow=true")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_run_logs_with_tail_and_task(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(2)
    response = await client.get(f"/api/runs/{run_id}/logs?tail=5&task=step1")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_clean_runs_no_params(client, setup_project, tmp_project):
    response = await client.delete("/api/runs/")
    assert response.status_code == 200
    data = response.json()
    assert data == {"deleted_runs": 0, "deleted_logs": 0}


@pytest.mark.asyncio
async def test_get_run_logs_task_not_found(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(2)
    response = await client.get(f"/api/runs/{run_id}/logs?task=nonexistent")
    assert response.status_code == 200
    data = response.json()
    assert data == {"logs": {}}
