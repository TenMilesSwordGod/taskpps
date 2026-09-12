"""凭据管理 API 测试（新增/查询/编辑/删除 + RBAC）。

设计决策（为什么这么写）：
- 每个测试用独立的函数级 workdir 作为项目目录，避免 session 级 tmp_project 被写脏。
- 走真实 ASGI + 真实 DB + 真实 YAML 文件，不 mock 文件系统，保证「加密落盘」这一
  安全承诺被直接验证（读文件断言无明文）。
- admin 通过 _seed_admin_account + 登录获取 token；普通用户通过注册获取，覆盖 RBAC。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import ProjectRepository
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.main import _seed_admin_account
from taskpps.main import app as _app
from tests.auth._helpers import auth_headers, register_user

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app():
    return _app


@pytest.fixture
async def project_dir(tmp_path, db_engine) -> Path:
    """创建函数级项目目录 + 注册项目记录，返回 workdir。"""
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


async def _user_headers(client: AsyncClient) -> dict[str, str]:
    await register_user(client, username="normal", nickname="Normal", password="pass123")
    resp = await client.post("/api/v1/auth/login", json={"username": "normal", "password": "pass123"})
    assert resp.status_code == 200
    return auth_headers(resp.json()["access_token"])


class TestCredentialCrud:
    async def test_create_then_list_without_secret(self, app, project_dir):
        """新增成功后列表只返回元数据，明文密码不落盘、不回传。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "project_id": pid,
                    "id": "prod-ssh",
                    "name": "生产 SSH",
                    "type": "ssh-username-password",
                    "username": "deploy",
                    "password": "super-secret",
                },
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["id"] == "prod-ssh"
            assert body["has_password"] is True
            assert "password" not in body

            listing = await client.get("/api/credentials/", headers=headers, params={"project_id": pid})
            assert listing.status_code == 200
            items = listing.json()
            assert [i["id"] for i in items] == ["prod-ssh"]
            assert "password" not in items[0]

        # 落盘文件必须是密文
        raw = (project_dir / "credentials" / "prod-ssh.yaml").read_text()
        assert "super-secret" not in raw
        assert "enc:v1:" in raw
        # loader 消费路径能拿到明文
        data = CredentialLoader(project_dir / "credentials").load("prod-ssh")
        assert data["password"] == "super-secret"
        assert data["username"] == "deploy"

    async def test_create_duplicate_returns_409(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            payload = {"project_id": pid, "id": "dup-cred", "password": "x"}
            first = await client.post("/api/credentials/", headers=headers, json=payload)
            assert first.status_code == 201
            second = await client.post("/api/credentials/", headers=headers, json=payload)
            assert second.status_code == 409

    async def test_create_invalid_id_returns_400(self, app, project_dir):
        """路径穿越/非法字符的 id 必须被拒绝（禁止写目录外文件）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            for bad_id in ("../evil", "a/b", ".hidden", "has space"):
                resp = await client.post(
                    "/api/credentials/",
                    headers=headers,
                    json={"project_id": pid, "id": bad_id, "password": "x"},
                )
                assert resp.status_code in (400, 422), f"id={bad_id} 应被拒绝"

    async def test_create_unknown_project_returns_404(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={"project_id": "no-such-project", "id": "c1", "password": "x"},
            )
            assert resp.status_code == 404

    async def test_create_with_missing_key_path_returns_400(self, app, project_dir):
        """key_path 指向服务端不存在的文件时拒绝保存，避免运行期才暴露。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "project_id": pid,
                    "id": "key-cred",
                    "type": "ssh-key",
                    "key_path": str(project_dir / "no-such-key"),
                },
            )
            assert resp.status_code == 400

    async def test_update_keeps_password_when_omitted(self, app, project_dir):
        """PUT 未传 password 时保留原密码（表单留空=不修改的语义）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            await client.post(
                "/api/credentials/",
                headers=headers,
                json={"project_id": pid, "id": "keep-cred", "password": "origin-pass"},
            )
            resp = await client.put(
                f"/api/credentials/{pid}/keep-cred",
                headers=headers,
                json={"name": "改名了"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["name"] == "改名了"
            assert resp.json()["has_password"] is True

        data = CredentialLoader(project_dir / "credentials").load("keep-cred")
        assert data["password"] == "origin-pass"

    async def test_update_empty_password_clears(self, app, project_dir):
        """PUT password="" 表示显式清除密码（改用 key_path 场景）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            await client.post(
                "/api/credentials/",
                headers=headers,
                json={"project_id": pid, "id": "clear-cred", "password": "origin-pass"},
            )
            resp = await client.put(
                f"/api/credentials/{pid}/clear-cred",
                headers=headers,
                json={"password": ""},
            )
            assert resp.status_code == 200
            assert resp.json()["has_password"] is False

        data = CredentialLoader(project_dir / "credentials").load("clear-cred")
        assert "password" not in data

    async def test_update_not_found_returns_404(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.put(
                f"/api/credentials/{pid}/ghost",
                headers=headers,
                json={"name": "x"},
            )
            assert resp.status_code == 404

    async def test_delete_credential(self, app, project_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            await client.post(
                "/api/credentials/",
                headers=headers,
                json={"project_id": pid, "id": "del-cred", "password": "x"},
            )
            resp = await client.delete(f"/api/credentials/{pid}/del-cred", headers=headers)
            assert resp.status_code == 200
            assert not (project_dir / "credentials" / "del-cred.yaml").exists()
            listing = await client.get("/api/credentials/", headers=headers, params={"project_id": pid})
            assert listing.json() == []

    async def test_delete_referenced_credential_returns_409(self, app, project_dir):
        """被 agent 引用的凭据禁止删除，返回 409 并告知引用方。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            await client.post(
                "/api/credentials/",
                headers=headers,
                json={"project_id": pid, "id": "in-use", "password": "x"},
            )
            (project_dir / "agents" / "srv-1.yaml").write_text(
                "host: 10.0.0.1\ncredential_id: in-use\n"
            )
            resp = await client.delete(f"/api/credentials/{pid}/in-use", headers=headers)
            assert resp.status_code == 409
            assert "srv-1" in resp.text

    async def test_edit_credential_in_list_file(self, app, project_dir):
        """列表形态 credentials: [...] 中的凭据也能编辑，且不破坏同文件其他条目。"""
        (project_dir / "credentials" / "group.yaml").write_text(
            "credentials:\n"
            "  - id: cred-a\n"
            "    username: ua\n"
            "    password: pa\n"
            "  - id: cred-b\n"
            "    username: ub\n"
            "    password: pb\n"
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _admin_headers(client)
            pid = await _project_id(project_dir)
            resp = await client.put(
                f"/api/credentials/{pid}/cred-a",
                headers=headers,
                json={"password": "new-pa"},
            )
            assert resp.status_code == 200, resp.text

        loader = CredentialLoader(project_dir / "credentials")
        all_creds = loader.load_all()
        assert all_creds["cred-a"]["password"] == "new-pa"
        assert all_creds["cred-b"]["password"] == "pb"


class TestCredentialRbac:
    async def test_guest_get_returns_403(self, app):
        """GET 列表无 token：中间件放行为 guest，RBAC 依赖必须返回 403。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/credentials/", params={"project_id": "any"})
            assert resp.status_code == 403

    async def test_normal_user_forbidden(self, app, project_dir):
        """普通用户（user 角色）不能读/写凭据。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            user_headers = await _user_headers(client)
            pid = await _project_id(project_dir)
            read = await client.get("/api/credentials/", headers=user_headers, params={"project_id": pid})
            assert read.status_code == 403
            write = await client.post(
                "/api/credentials/",
                headers=user_headers,
                json={"project_id": pid, "id": "nope", "password": "x"},
            )
            assert write.status_code == 403

    async def test_guest_post_returns_401(self, app, project_dir):
        """无 token POST 由中间件直接 401（未进入 RBAC 依赖）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            pid = await _project_id(project_dir)
            resp = await client.post(
                "/api/credentials/",
                json={"project_id": pid, "id": "nope", "password": "x"},
            )
            assert resp.status_code == 401
