import pytest
from unittest.mock import patch, MagicMock
from taskpps.__main__ import main
from taskpps.main import mark_external_engine, cli, lifespan, app
from taskpps.db.engine import reset_engine


def test_main_module_main():
    with patch("taskpps.__main__.load_settings") as mock_load:
        with patch("taskpps.__main__.get_settings") as mock_get:
            with patch("taskpps.__main__.uvicorn.run") as mock_run:
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
    from taskpps.main import _external_engine
    old_val = _external_engine
    mark_external_engine()
    from taskpps.main import _external_engine
    assert _external_engine is True


def test_cli():
    with patch("taskpps.main.load_settings") as mock_load:
        with patch("taskpps.main.get_settings") as mock_get:
            with patch("taskpps.main.uvicorn.run") as mock_run:
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
    from taskpps.main import _plugin_manager, _external_engine
    _external_engine = True

    async with lifespan(app):
        pass


@pytest.mark.asyncio
async def test_lifespan_with_settings_none():
    reset_engine()
    import taskpps.config as cfg
    cfg._settings = None
    cfg._project_root = None

    from taskpps.main import _external_engine
    _external_engine = True

    with patch("taskpps.main.init_db") as mock_init:
        async with lifespan(app):
            pass
        mock_init.assert_called_once()
