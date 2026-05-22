import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from taskpps.main import app


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_run(client, setup_project, tmp_project):
    response = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["pipeline_name"] == "deploy"


@pytest.mark.asyncio
async def test_create_run_with_params(client, setup_project, tmp_project):
    response = await client.post(
        "/api/runs/",
        json={"pipeline": "deploy.yaml", "params": {"options.host": "prod-server"}},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_run_not_found(client, setup_project, tmp_project):
    response = await client.post("/api/runs/", json={"pipeline": "nonexistent.yaml"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_run_cycle(client, setup_project, tmp_project):
    response = await client.post("/api/runs/", json={"pipeline": "cycle.yaml"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_runs(client, setup_project, tmp_project):
    await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    response = await client.get("/api/runs/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_list_runs_filter(client, setup_project, tmp_project):
    await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    response = await client.get("/api/runs/?pipeline=deploy")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_run(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    run_id = create_resp.json()["id"]
    await asyncio.sleep(1)
    response = await client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id
    assert "tasks" in data


@pytest.mark.asyncio
async def test_get_run_not_found(client, setup_project, tmp_project):
    response = await client.get("/api/runs/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_logs(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(2)
    response = await client.get(f"/api/runs/{run_id}/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data


@pytest.mark.asyncio
async def test_get_run_logs_with_task(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(2)
    response = await client.get(f"/api/runs/{run_id}/logs?task=step1")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_run_logs_with_tail(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(2)
    response = await client.get(f"/api/runs/{run_id}/logs?tail=10")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cancel_run(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    run_id = create_resp.json()["id"]
    response = await client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_nonexistent_run(client, setup_project, tmp_project):
    response = await client.post("/api/runs/nonexistent/cancel")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_clean_runs_force(client, setup_project, tmp_project):
    await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    await asyncio.sleep(1)
    response = await client.delete("/api/runs/?force=true")
    assert response.status_code == 200
    data = response.json()
    assert data["deleted_runs"] >= 1


@pytest.mark.asyncio
async def test_clean_runs_keep(client, setup_project, tmp_project):
    await client.post("/api/runs/", json={"pipeline": "deploy.yaml"})
    await asyncio.sleep(1)
    response = await client.delete("/api/runs/?keep=5")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_clean_runs_older_than(client, setup_project, tmp_project):
    response = await client.delete("/api/runs/?older_than=7")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_trigger(client, setup_project, tmp_project):
    response = await client.post(
        "/api/plugins/triggers/",
        json={
            "type": "cron",
            "config": {"schedule": "0 * * * *"},
            "pipeline_file": "deploy.yaml",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["type"] == "cron"


@pytest.mark.asyncio
async def test_list_triggers(client, setup_project, tmp_project):
    await client.post(
        "/api/plugins/triggers/",
        json={
            "type": "cron",
            "config": {"schedule": "0 * * * *"},
            "pipeline_file": "deploy.yaml",
        },
    )
    response = await client.get("/api/plugins/triggers/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_delete_trigger(client, setup_project, tmp_project):
    create_resp = await client.post(
        "/api/plugins/triggers/",
        json={
            "type": "cron",
            "config": {"schedule": "0 * * * *"},
            "pipeline_file": "deploy.yaml",
        },
    )
    trigger_id = create_resp.json()["id"]
    response = await client.delete(f"/api/plugins/triggers/{trigger_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_trigger_not_found(client, setup_project, tmp_project):
    response = await client.delete("/api/plugins/triggers/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_simple_pipeline(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "simple.yaml"})
    if create_resp.status_code != 201:
        pytest.fail(f"Expected 201, got {create_resp.status_code}: {create_resp.text}")
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(3)
    get_resp = await client.get(f"/api/runs/{run_id}")
    data = get_resp.json()
    assert data["status"] in ("success", "running", "pending", "partial")


@pytest.mark.asyncio
async def test_run_fail_pipeline(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "fail_test.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(3)
    get_resp = await client.get(f"/api/runs/{run_id}")
    data = get_resp.json()
    assert data["status"] in ("failed", "partial", "running")


@pytest.mark.asyncio
async def test_run_continue_pipeline(client, setup_project, tmp_project):
    create_resp = await client.post("/api/runs/", json={"pipeline": "continue_test.yaml"})
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]
    await asyncio.sleep(3)
    get_resp = await client.get(f"/api/runs/{run_id}")
    data = get_resp.json()
    task_names = [t["task_name"] for t in data.get("tasks", [])]
    assert "independent" in task_names
