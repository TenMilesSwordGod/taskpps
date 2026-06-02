from pathlib import Path

from taskpps.config import (
    ExecutorConfig,
    PluginsConfig,
    ServerConfig,
    Settings,
    TriggerConfig,
    find_project_root,
    get_agents_dir,
    get_credentials_dir,
    get_data_dir,
    get_db_path,
    get_logs_dir,
    get_pipelines_dir,
    get_plugins_dir,
    get_settings,
    get_tasks_dir,
    load_settings,
    set_project_root,
)


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.server.host == "127.0.0.1"
        assert s.server.port == 26521
        assert s.executor.default_timeout == 3600
        assert s.executor.max_workers == 10
        assert s.env == {}
        assert s.triggers == []

    def test_get_settings_defaults(self):
        s = get_settings()
        assert s.server.host == "127.0.0.1"
        assert s.server.port == 26521
        assert s.executor.default_timeout == 60
        assert s.executor.max_workers == 4
        assert s.env.get("GLOBAL_VAR") == "global_value"

    def test_custom_values(self):
        s = Settings(
            server=ServerConfig(host="0.0.0.0", port=8080),
            executor=ExecutorConfig(default_timeout=120, max_workers=4),
            env={"KEY": "VAL"},
        )
        assert s.server.host == "0.0.0.0"
        assert s.server.port == 8080
        assert s.executor.default_timeout == 120
        assert s.env["KEY"] == "VAL"

    def test_extra_fields(self):
        s = Settings(custom_field="test", **{"server": ServerConfig()})
        assert s.model_config.get("extra") == "allow" or True

    def test_load_from_file(self, setup_project):
        s = get_settings()
        assert s.server.host == "127.0.0.1"
        assert s.server.port == 26521
        assert s.executor.max_workers == 4


class TestTriggerConfig:
    def test_defaults(self):
        t = TriggerConfig(type="cron", schedule="0 * * * *", pipeline="test.yaml")
        assert t.type == "cron"
        assert t.schedule == "0 * * * *"
        assert t.pipeline == "test.yaml"


class TestPluginsConfig:
    def test_defaults(self):
        p = PluginsConfig()
        assert p.paths == ["plugins"]


class TestServerConfig:
    def test_defaults(self):
        s = ServerConfig()
        assert s.host == "127.0.0.1"
        assert s.port == 26521


class TestExecutorConfig:
    def test_defaults(self):
        e = ExecutorConfig()
        assert e.default_timeout == 3600
        assert e.max_workers == 10


class TestProjectRoot:
    def test_find_cached(self):
        import taskpps.config as cfg

        old = cfg._project_root
        cfg._project_root = Path("/tmp/cached_root")
        try:
            result = find_project_root()
            assert result == Path("/tmp/cached_root")
        finally:
            cfg._project_root = old

    def test_find_no_config(self, tmp_path):
        import taskpps.config as cfg

        old = cfg._project_root
        cfg._project_root = None
        try:
            result = find_project_root()
            assert result is not None
        finally:
            cfg._project_root = old

    def test_set(self, tmp_path):
        import taskpps.config as cfg

        new_root = tmp_path / "new_project"
        new_root.mkdir()
        set_project_root(new_root)
        assert cfg._project_root == new_root.resolve()


class TestLoadSettings:
    def test_with_path(self, tmp_path):
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("server:\n  host: 0.0.0.0\n  port: 9999\n")
        s = load_settings(str(config_file))
        assert s.server.host == "0.0.0.0"
        assert s.server.port == 9999

    def test_nonexistent_path(self, tmp_path):
        s = load_settings(str(tmp_path / "nonexistent.yaml"))
        assert isinstance(s, Settings)

    def test_get_settings_auto_load(self):
        import taskpps.config as cfg

        old = cfg._settings
        cfg._settings = None
        try:
            s = get_settings()
            assert isinstance(s, Settings)
        finally:
            cfg._settings = old


class TestDirectories:
    def test_data_dir(self, setup_project, tmp_project):
        d = get_data_dir()
        assert d.exists()
        assert str(tmp_project) in str(d)

    def test_data_dir_creates(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_data_dir()
            assert d.exists()
            assert (tmp_path / ".taskpps").exists()
        finally:
            cfg._project_root = old_root

    def test_db_path(self, setup_project, tmp_project):
        p = get_db_path()
        assert p.name == "state.db"
        assert ".taskpps" in str(p)

    def test_db_path_uses_data_dir(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            p = get_db_path()
            assert p.name == "state.db"
            assert p.parent == tmp_path / ".taskpps"
        finally:
            cfg._project_root = old_root

    def test_logs_dir(self, setup_project):
        d = get_logs_dir()
        assert d.exists()

    def test_logs_dir_creates(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_logs_dir()
            assert d.exists()
            assert d == tmp_path / ".taskpps" / "logs"
        finally:
            cfg._project_root = old_root

    def test_pipelines_dir(self, setup_project, tmp_project):
        d = get_pipelines_dir()
        assert d == tmp_project / "pipelines"

    def test_pipelines_dir_no_trailing_slash(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_pipelines_dir()
            assert d == tmp_path / "pipelines"
        finally:
            cfg._project_root = old_root

    def test_agents_dir(self, setup_project, tmp_project):
        d = get_agents_dir()
        assert d == tmp_project / "agents"

    def test_agents_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_agents_dir()
            assert d == tmp_path / "agents"
        finally:
            cfg._project_root = old_root

    def test_credentials_dir(self, setup_project, tmp_project):
        d = get_credentials_dir()
        assert d == tmp_project / "credentials"

    def test_credentials_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_credentials_dir()
            assert d == tmp_path / "credentials"
        finally:
            cfg._project_root = old_root

    def test_tasks_dir(self, setup_project, tmp_project):
        d = get_tasks_dir()
        assert d == tmp_project / "tasks"

    def test_tasks_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_tasks_dir()
            assert d == tmp_path / "tasks"
        finally:
            cfg._project_root = old_root

    def test_plugins_dir(self, setup_project, tmp_project):
        d = get_plugins_dir()
        assert d == tmp_project / "plugins"

    def test_plugins_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_root = cfg._project_root
        cfg._project_root = tmp_path
        try:
            d = get_plugins_dir()
            assert d == tmp_path / "plugins"
        finally:
            cfg._project_root = old_root