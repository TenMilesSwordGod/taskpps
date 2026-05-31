from unittest.mock import MagicMock, patch

import pytest

import taskpps.config as cfg
import taskpps.main as main_mod
from taskpps.__main__ import main
from taskpps.db.engine import reset_engine
from taskpps.main import app, cli, lifespan, mark_external_engine


def test_main_module_main():
    with (
        patch("taskpps.__main__.load_settings") as mock_load,
        patch("taskpps.__main__.get_settings") as mock_get,
        patch("taskpps.__main__.uvicorn.run") as mock_run,
    ):
        mock_settings = MagicMock()
        mock_settings.server.host = "127.0.0.1"
        mock_settings.server.port = 26521
        mock_get.return_value = mock_settings
        main()
        mock_load.assert_called_once()
        mock_run.assert_called_once_with(
            "taskpps.main:app",
            host="127.0.0.1",
            port=26521,
            reload=False,
        )


def test_mark_external_engine():
    reset_engine()
    mark_external_engine()
    assert main_mod._external_engine is True


def test_cli():
    with (
        patch("taskpps.main.load_settings") as mock_load,
        patch("taskpps.main.get_settings") as mock_get,
        patch("taskpps.main.uvicorn.run") as mock_run,
    ):
        mock_settings = MagicMock()
        mock_settings.server.host = "0.0.0.0"
        mock_settings.server.port = 8080
        mock_get.return_value = mock_settings
        cli()
        mock_load.assert_called_once()
        mock_run.assert_called_once_with(
            "taskpps.main:app",
            host="0.0.0.0",
            port=8080,
            reload=False,
        )


@pytest.mark.asyncio
async def test_lifespan():
    reset_engine()
    main_mod._external_engine = True

    async with lifespan(app):
        pass


@pytest.mark.asyncio
async def test_lifespan_with_settings_none():
    reset_engine()
    cfg._settings = None
    cfg._project_root = None

    main_mod._external_engine = True

    with patch("taskpps.main.init_db") as mock_init:
        async with lifespan(app):
            pass
        mock_init.assert_called_once()
