from __future__ import annotations

import pytest

from taskpps.main import app as _app


class TestAppCreation:
    def test_create_app(self):
        assert _app is not None
        assert _app.title is not None

    def test_create_app_routes(self):
        routes = [r.path for r in _app.routes]
        assert "/api/health" in routes
        assert "/api/runs/" in routes


class TestAppLifespan:
    @pytest.mark.asyncio
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
