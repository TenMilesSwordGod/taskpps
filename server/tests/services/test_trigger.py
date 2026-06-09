from __future__ import annotations

import pytest

from taskpps.services.trigger_service import TriggerService


def _setup_config(tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


class TestTriggerService:
    @pytest.mark.asyncio
    async def test_create_and_list(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = TriggerService()
        result = await svc.create_trigger("cron", {"schedule": "0 * * * *"}, "deploy.yaml")
        assert hasattr(result, "id")

        triggers = await svc.list_triggers()
        assert len(triggers) >= 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_project, db_engine):
        _setup_config(tmp_project)
        svc = TriggerService()
        result = await svc.delete_trigger("nonexistent")
        assert result is False
