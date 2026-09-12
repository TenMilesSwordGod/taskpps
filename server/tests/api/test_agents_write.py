"""Agent 配置写接口测试（新增/编辑/删除 + 引用检查 + RBAC）。

设计决策（为什么断言文件内容而非仅接口返回）：
- 网页写接口的契约是「YAML 文件即数据源」，因此必须验证未知字段保留、
  列表文件原地更新、删除真正落盘，避免只测 HTTP 层产生假安全感。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.api.agents import invalidate_agents_cache
from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ProjectRepository
from taskpps.main import _seed_admin_account
from taskpps.main import app as _app
from tests.auth._helpers import auth_headers, register_user

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app():
    return _app


@pytest.fixture(autouse=True)
def _clear_agents_cache():
    invalidate_agents_cache()
    yield
    invalidate_agents_cache()


@pytest.fixture
async def project_dir(tmp_path, db_engine) -> Path:
    workdir = tmp_path / "proj"
    (workdir / "agents").mkdir(parents=True)
    (workdir / "credentials").mkdir(parents=True)
    (workdir / "pipelines").mkdir(parents=True)
    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        await repo.create_project(workdir=str(workdir), name="测试项目")
    return workdir


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    await _seed_admin_account()
    resp = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "user@123"})
    assert resp.status_code == 200, resp.text
    return auth_headers(resp.json()["access_token"])


async def _project_id(workdir: Path) -> str:
    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        project = await repo.get_project_by_workdir(str(workdir))
        assert project is not None
        return project.id


class TestAgentConfigCrud:
    async def test_create_then_appears_in_all(self, app, project_dir):
        """新增后立刻能在 /agents/all 看到，且编辑字段（credential_id/username）回填。"""
        (project_dir / "credentials" / "c1.yaml").write_text("username: deploy\npassword: p\n")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "project_id": pid,
                    "id": "web-1",
                    "name": "Web 1",
                    "type": "ssh-username-password",
                    "host": "10.0.0.1",
                    "port": 2222,
                    "username": "deploy",
                    "credential_id": "c1",
                    "max_parallel": 2,
                },
            )
            assert resp.status_code == 201, resp.text

            listing = await client.get("/api/agents/all")
            assert listing.status_code == 200
            item = next((a for a in listing.json() if a["agent_id"] == "web-1"), None)
            assert item is not None
            assert item["credential_id"] == "c1"
            assert item["username"] == "deploy"
            assert item["port"] == 2222
            assert item["project_id"] == pid

        data = (project_dir / "agents" / "web-1.yaml").read_text()
        assert "host: 10.0.0.1" in data
        assert "credential_id: c1" in data

    async def test_create_duplicate_returns_409(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            payload = {"project_id": pid, "id": "dup", "host": "1.1.1.1"}
            assert (await client.post("/api/agents/", headers=headers, json=payload)).status_code == 201
            assert (await client.post("/api/agents/", headers=headers, json=payload)).status_code == 409

    async def test_create_invalid_id_returns_4xx(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            for bad_id in ("../evil", "a/b", ".hidden"):
                resp = await client.post(
                    "/api/agents/",
                    headers=headers,
                    json={"project_id": pid, "id": bad_id, "host": "1.1.1.1"},
                )
                assert resp.status_code in (400, 422), f"id={bad_id} 应被拒绝"

    async def test_create_unknown_project_returns_404(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={"project_id": "ghost", "id": "a1", "host": "1.1.1.1"},
            )
            assert resp.status_code == 404

    async def test_create_with_missing_credential_returns_400(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={"project_id": pid, "id": "a1", "host": "1.1.1.1", "credential_id": "nope"},
            )
            assert resp.status_code == 400

    async def test_update_preserves_unknown_fields(self, app, project_dir):
        """编辑只覆盖表单字段，agent_binary_path 等运维高级字段必须保留。"""
        (project_dir / "agents" / "keep.yaml").write_text(
            "host: 10.0.0.9\nport: 22\nname: Old\n"
            "agent_binary_path: /opt/custom/agent\n"
            "agent_auto_bootstrap: false\n"
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.put(
                f"/api/agents/{pid}/keep",
                headers=headers,
                json={"name": "New", "port": 2200},
            )
            assert resp.status_code == 200, resp.text

        data = (project_dir / "agents" / "keep.yaml").read_text()
        assert "name: New" in data
        assert "port: 2200" in data
        assert "agent_binary_path: /opt/custom/agent" in data

    async def test_update_not_found_returns_404(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.put(
                f"/api/agents/{pid}/ghost",
                headers=headers,
                json={"name": "x"},
            )
            assert resp.status_code == 404

    async def test_delete_agent(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            await client.post(
                "/api/agents/",
                headers=headers,
                json={"project_id": pid, "id": "del-me", "host": "1.1.1.1"},
            )
            resp = await client.delete(f"/api/agents/{pid}/del-me", headers=headers)
            assert resp.status_code == 200
            assert not (project_dir / "agents" / "del-me.yaml").exists()
            assert (await client.delete(f"/api/agents/{pid}/del-me", headers=headers)).status_code == 404

    async def test_delete_referenced_agent_returns_409(self, app, project_dir):
        """被流水线 host 引用的服务器禁止删除，并返回引用文件名。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            await client.post(
                "/api/agents/",
                headers=headers,
                json={"project_id": pid, "id": "in-use", "host": "1.1.1.1"},
            )
            (project_dir / "pipelines" / "deploy.yaml").write_text(
                "name: deploy\ntasks:\n  - name: t1\n    command: echo hi\n    host: in-use\n"
            )
            resp = await client.delete(f"/api/agents/{pid}/in-use", headers=headers)
            assert resp.status_code == 409
            assert "deploy.yaml" in resp.text

    async def test_update_agent_in_list_file(self, app, project_dir):
        """列表文件 agents: [...] 内条目原地更新且不影响同文件其他 agent。"""
        (project_dir / "agents" / "ssh.yaml").write_text(
            "agents:\n"
            "  - id: a1\n"
            "    host: 1.1.1.1\n"
            "    name: A1\n"
            "  - id: a2\n"
            "    host: 2.2.2.2\n"
            "    name: A2\n"
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.put(
                f"/api/agents/{pid}/a1",
                headers=headers,
                json={"host": "9.9.9.9"},
            )
            assert resp.status_code == 200, resp.text

        import yaml

        doc = yaml.safe_load((project_dir / "agents" / "ssh.yaml").read_text())
        by_id = {a["id"]: a for a in doc["agents"]}
        assert by_id["a1"]["host"] == "9.9.9.9"
        assert by_id["a2"]["host"] == "2.2.2.2"

    async def test_try_connect_uses_project_credential(self, app, project_dir):
        """回归：非默认项目的「测试连接」必须能解析同项目凭据。

        修复前 try-connect 在 event loop 内回退默认 workdir，报 "Credential not found"。
        这里通过项目级 agent+credential 触发 SSH 认证（端口 1 必然拒绝），
        断言错误来自网络层而非"凭据不存在"。
        """
        (project_dir / "credentials" / "c1.yaml").write_text("username: deploy\npassword: p\n")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            created = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "project_id": pid,
                    "id": "probe-1",
                    "type": "ssh-username-password",
                    "host": "127.0.0.1",
                    "port": 1,
                    "credential_id": "c1",
                },
            )
            assert created.status_code == 201, created.text

            resp = await client.post(
                "/api/agents/try-connect",
                headers=headers,
                json={"agent_id": "probe-1", "timeout": 1},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["agent_id"] == "probe-1"
            assert body["status"] != "connected"
            assert "Credential not found" not in (body.get("error") or "")


class TestAgentConfigRbac:
    async def test_guest_get_all_still_readable(self, app, project_dir):
        """服务器列表是 GET，guest 也可读（保持现状，不因 RBAC 收紧）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/agents/all")
            assert resp.status_code == 200

    async def test_normal_user_cannot_write(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await register_user(client, username="normal", nickname="Normal", password="pass123")
            login = await client.post("/api/v1/auth/login", json={"username": "normal", "password": "pass123"})
            headers = auth_headers(login.json()["access_token"])
            pid = await _project_id(project_dir)
            create = await client.post(
                "/api/agents/",
                headers=headers,
                json={"project_id": pid, "id": "nope", "host": "1.1.1.1"},
            )
            assert create.status_code == 403

            (project_dir / "agents" / "victim.yaml").write_text("host: 1.1.1.1\n")
            update = await client.put(
                f"/api/agents/{pid}/victim",
                headers=headers,
                json={"name": "hacked"},
            )
            delete = await client.delete(f"/api/agents/{pid}/victim", headers=headers)
            assert update.status_code == 403
            assert delete.status_code == 403

    async def test_guest_post_returns_401(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pid = await _project_id(project_dir)
            resp = await client.post(
                "/api/agents/",
                json={"project_id": pid, "id": "nope", "host": "1.1.1.1"},
            )
            assert resp.status_code == 401
