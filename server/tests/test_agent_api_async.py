import pytest


@pytest.mark.asyncio
async def test_agent_try_connect_local(client):
    resp = await client.post("/api/agents/try-connect", json={
        "agent_id": "api-agent-a",
        "timeout": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["agent_id"] == "api-agent-a"
    assert "ssh.yaml" in data["source_file"]


@pytest.mark.asyncio
async def test_agent_try_connect_not_found(client):
    resp = await client.post("/api/agents/try-connect", json={
        "agent_id": "nonexistent",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_check_all(client):
    resp = await client.post("/api/agents/check", json={
        "timeout": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "summary" in data
    assert data["summary"]["total"] >= 1


@pytest.mark.asyncio
async def test_agent_check_single(client):
    resp = await client.post("/api/agents/check", json={
        "agent_id": "api-agent-a",
        "timeout": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total"] == 1
    assert data["results"][0]["agent_id"] == "api-agent-a"


@pytest.mark.asyncio
async def test_agent_check_file_filter(client):
    resp = await client.post("/api/agents/check", json={
        "file_filter": "ssh",
        "timeout": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    for r in data["results"]:
        assert "agents/ssh.yaml" in r["source_file"]


@pytest.mark.asyncio
async def test_agent_check_stream(client):
    resp = await client.post("/api/agents/check-stream", json={
        "timeout": 5,
    })
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    body = resp.text
    lines = body.strip().split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]

    assert len(data_lines) >= 2

    agent_ids = []
    has_summary = False
    for line in data_lines:
        content = line.removeprefix("data: ")
        if content.startswith("summary:"):
            has_summary = True
        else:
            import json
            r = json.loads(content)
            assert "agent_id" in r
            assert "status" in r
            agent_ids.append(r["agent_id"])

    assert has_summary
    assert "api-agent-a" in agent_ids


@pytest.mark.asyncio
async def test_agent_check_stream_single(client):
    resp = await client.post("/api/agents/check-stream", json={
        "agent_id": "api-agent-a",
        "timeout": 5,
    })
    assert resp.status_code == 200

    body = resp.text
    lines = body.strip().split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]

    assert len(data_lines) == 2
    assert data_lines[0].startswith("data: ") and not data_lines[0].startswith("data: summary:")
    assert data_lines[1].startswith("data: summary:")


@pytest.mark.asyncio
async def test_agent_check_stream_file_filter(client):
    resp = await client.post("/api/agents/check-stream", json={
        "file_filter": "ssh",
        "timeout": 5,
    })
    assert resp.status_code == 200

    body = resp.text
    lines = body.strip().split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]

    for line in data_lines[:-1]:
        content = line.removeprefix("data: ")
        if not content.startswith("summary:"):
            import json
            r = json.loads(content)
            assert "ssh.yaml" in r["source_file"]