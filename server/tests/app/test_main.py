from __future__ import annotations

import pytest

from taskpps.main import app as _app


class TestAppCreation:
    @pytest.mark.zentao("TC-S0038", domain="server/app", priority="P0")
    def test_create_app(self):
        assert _app is not None
        assert _app.title is not None

    @pytest.mark.zentao("TC-S0039", domain="server/app", priority="P0")
    def test_create_app_routes(self):
        routes = [r.path for r in _app.routes]
        assert "/api/health" in routes
        assert "/api/runs/" in routes


class TestAppLifespan:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0040", domain="server/app", priority="P2")
    async def test_app_lifespan(self, setup_project, tmp_project):
        import taskpps.config as cfg

        cfg.set_project_root(tmp_project)
        cfg._settings = None
        cfg.load_settings(str(tmp_project / "taskpps.yaml"))

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200

