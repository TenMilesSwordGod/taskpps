from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.main import app as _app


@pytest.fixture
def app():
    return _app


@pytest.mark.asyncio
async def test_concurrent_list_api_no_duplicate_definitions(app, setup_project, tmp_project, db_engine, clean_db):
    """并发调用列表 API 不会产生重复 definition 记录。
    并发使用 asyncio.gather() 发起多个请求，验证 id 一致性。
    SQLite 文件 DB 下并发写有局限，此测试主要验证幂等语义。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/projects/",
            json={"workdir": str(tmp_project), "name": "my-project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        resp1 = await client.get("/api/pipelines/", params={"project_id": project_id})
        assert resp1.status_code == 200
        items1 = resp1.json()["items"]
        ids1 = {item["id"] for item in items1}

        async def call_list():
            resp = await client.get("/api/pipelines/", params={"project_id": project_id})
            assert resp.status_code == 200
            return {item["id"] for item in resp.json()["items"]}

        results = await asyncio.gather(call_list(), call_list(), call_list(), call_list(), call_list())
        for ids in results:
            assert ids == ids1

        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import PipelineDefinitionRepository

        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            definitions = await repo.list_by_project(project_id)
            assert len(definitions) == len(items1)


@pytest.mark.asyncio
async def test_sequential_add_files_no_duplicate(app, setup_project, tmp_project, db_engine, clean_db):
    created_files = []
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            from pathlib import Path

            names = ["seq_a", "seq_b", "seq_c"]
            for name in names:
                yfile = Path(tmp_project) / "pipelines" / f"{name}.yaml"
                yfile.write_text(f"name: {name}\noptions: {{}}\ntasks:\n  - name: t1\n    command: echo {name}\n")
                created_files.append(yfile)
                resp = await client.get("/api/pipelines/", params={"project_id": project_id})
                assert resp.status_code == 200
                items = resp.json()["items"]
                assert any(i["name"] == name for i in items)

            from taskpps.db.engine import get_session_factory
            from taskpps.db.repository import PipelineDefinitionRepository

            async with get_session_factory()() as session:
                repo = PipelineDefinitionRepository(session)
                definitions = await repo.list_by_project(project_id)
                seq_defs = [d for d in definitions if d.file_path.startswith("seq_")]
                assert len(seq_defs) == 3
                assert all(d.active for d in seq_defs)
    finally:
        for f in created_files:
            if f.exists():
                f.unlink()


@pytest.mark.asyncio
async def test_sequential_put_save_idempotent(app, setup_project, tmp_project, db_engine, clean_db):
    put_path = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/projects/",
                json={"workdir": str(tmp_project), "name": "my-project"},
            )
            assert create_resp.status_code == 201
            project_id = create_resp.json()["id"]

            yaml_content = (
                "name: seq_put\n"
                "options:\n"
                "  on_failure: continue\n"
                "tasks:\n"
                "  - name: t1\n"
                "    command: echo hi\n"
            )

            put_path = Path(tmp_project) / "pipelines" / "seq_put.yaml"
            for _ in range(3):
                resp = await client.put(
                    "/api/pipelines/seq_put.yaml",
                    json={"content": yaml_content},
                    params={"project_id": project_id},
                )
                assert resp.status_code == 200

            from taskpps.db.engine import get_session_factory
            from taskpps.db.repository import PipelineDefinitionRepository

            async with get_session_factory()() as session:
                repo = PipelineDefinitionRepository(session)
                definitions = await repo.list_by_project(project_id)
                seq_defs = [d for d in definitions if d.file_path == "seq_put.yaml"]
                assert len(seq_defs) == 1
                assert seq_defs[0].active is True
    finally:
        if put_path and put_path.exists():
            put_path.unlink()
