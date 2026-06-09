from __future__ import annotations

import pytest

from taskpps.config import (
    Settings,
    compute_pipeline_id,
    compute_pipeline_version,
    get_project_workdir,
    get_server_home,
    get_settings,
    load_settings,
    set_project_root,
)


class TestConfigBoundary:
    def test_load_empty_yaml(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        s = load_settings(str(config_file))
        assert isinstance(s, Settings)

    def test_load_null_yaml(self, tmp_path):
        config_file = tmp_path / "null.yaml"
        config_file.write_text("null")
        s = load_settings(str(config_file))
        assert isinstance(s, Settings)

    def test_load_partial_config(self, tmp_path):
        config_file = tmp_path / "partial.yaml"
        config_file.write_text("server:\n  port: 9999\n")
        s = load_settings(str(config_file))
        assert s.server.port == 9999
        assert s.server.host == "127.0.0.1"

    def test_load_extra_fields(self, tmp_path):
        config_file = tmp_path / "extra.yaml"
        config_file.write_text("custom_field: value\nserver:\n  host: 0.0.0.0\n")
        s = load_settings(str(config_file))
        assert s.server.host == "0.0.0.0"

    def test_load_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text(":invalid: yaml: [[")
        import yaml

        with pytest.raises(yaml.YAMLError):
            load_settings(str(config_file))

    def test_get_settings_resets(self):
        import taskpps.config as cfg

        old = cfg._settings
        cfg._settings = None
        try:
            s = get_settings()
            assert isinstance(s, Settings)
        finally:
            cfg._settings = old

    def test_set_project_root_resets_globals(self, tmp_path):
        import taskpps.config as cfg

        old_root = cfg._project_root
        old_home = cfg._server_home
        old_workdir = cfg._project_workdir

        new_root = tmp_path / "test_root"
        new_root.mkdir()
        set_project_root(new_root)

        try:
            assert cfg._project_root == new_root.resolve()
            assert cfg._server_home == new_root.resolve()
            assert cfg._project_workdir == new_root.resolve()
        finally:
            cfg._project_root = old_root
            cfg._server_home = old_home
            cfg._project_workdir = old_workdir

    def test_compute_pipeline_id_simple(self):
        result = compute_pipeline_id("deploy.yaml")
        assert result == "deploy"

    def test_compute_pipeline_id_nested(self):
        result = compute_pipeline_id("apps/deploy.yaml")
        assert result == "apps_deploy"

    def test_compute_pipeline_id_multiple_extensions(self):
        result = compute_pipeline_id("test.tar.gz")
        assert result == "test.tar"

    def test_compute_pipeline_id_no_extension(self):
        result = compute_pipeline_id("Makefile")
        assert result == "Makefile"

    def test_compute_pipeline_id_empty(self):
        with pytest.raises(ValueError):
            compute_pipeline_id("")

    def test_compute_pipeline_id_deep_nested(self):
        result = compute_pipeline_id("a/b/c/d/e/deploy.yaml")
        assert result == "a_b_c_d_e_deploy"

    def test_get_project_workdir_from_env(self, tmp_path, monkeypatch):
        import taskpps.config as cfg

        old = cfg._project_workdir
        cfg._project_workdir = None
        monkeypatch.setenv("TASKPPS_WORKDIR", str(tmp_path))
        try:
            result = get_project_workdir()
            assert result == tmp_path
        finally:
            cfg._project_workdir = old

    def test_get_project_workdir_from_settings(self, tmp_path, setup_project, monkeypatch):
        import taskpps.config as cfg

        old = cfg._project_workdir
        cfg._project_workdir = None
        monkeypatch.delenv("TASKPPS_WORKDIR", raising=False)
        old_settings = cfg._settings
        cfg._settings = Settings(workdir=str(tmp_path))
        try:
            result = get_project_workdir()
            assert result == tmp_path
        finally:
            cfg._project_workdir = old
            cfg._settings = old_settings

    def test_get_server_home_from_env(self, tmp_path, monkeypatch):
        import taskpps.config as cfg

        old = cfg._server_home
        cfg._server_home = None
        monkeypatch.setenv("TASKPPS_SERVER_HOME", str(tmp_path))
        try:
            result = get_server_home()
            assert result == tmp_path
        finally:
            cfg._server_home = old

    def test_get_server_home_fallback_to_code_path(self, setup_project, monkeypatch):
        import taskpps.config as cfg

        old = cfg._server_home
        cfg._server_home = None
        monkeypatch.delenv("TASKPPS_SERVER_HOME", raising=False)
        try:
            result = get_server_home()
            # get_server_home() 不读 settings，当 _server_home=None 且无环境变量时回退到代码路径
            from pathlib import Path

            expected = Path(__file__).resolve().parent.parent.parent.parent
            assert result == expected
        finally:
            cfg._server_home = old

    def test_compute_pipeline_version_nonexistent(self):
        result = compute_pipeline_version("nonexistent.yaml")
        assert result == ""
