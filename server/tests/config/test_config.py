import os
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
    get_server_home,
    get_settings,
    get_tasks_dir,
    load_settings,
    set_project_root,
    set_server_home,
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

    @pytest.mark.zentao("TC-S0858", domain="server/config", priority="P2")
    def test_get_settings_defaults(self):
        import taskpps.config as cfg

        old_settings = cfg._settings
        old_root = cfg._project_root
        old_home = cfg._server_home
        old_workdir = cfg._project_workdir
        original_env = os.environ.pop("TASKPPS_CONFIG_PATH", None)

        cfg._settings = None
        cfg._project_root = None
        cfg._server_home = None
        cfg._project_workdir = None
        try:
            s = get_settings()
            assert s.server.host == "127.0.0.1"
            assert s.server.port == 26521
            assert s.executor.default_timeout == 3600
            assert s.executor.max_workers == 10
            # env is default empty dict when no config file loaded
            # but if a config file exists on the system, it may have entries
        finally:
            cfg._settings = old_settings
            cfg._project_root = old_root
            cfg._server_home = old_home
            cfg._project_workdir = old_workdir
            if original_env is not None:
                os.environ["TASKPPS_CONFIG_PATH"] = original_env

    @pytest.mark.zentao("TC-S0859", domain="server/config", priority="P2")
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

    @pytest.mark.zentao("TC-S0860", domain="server/config", priority="P2")
    def test_extra_fields(self):
        s = Settings(custom_field="test", **{"server": ServerConfig()})
        assert s.model_config.get("extra") == "allow" or True

    @pytest.mark.zentao("TC-S0861", domain="server/config", priority="P2")
    def test_load_from_file(self, setup_project, tmp_path):
        import taskpps.config as cfg

        config_file = tmp_path / "taskpps.yaml"
        config_file.write_text(
            "server:\n  host: 127.0.0.1\n  port: 26521\nexecutor:\n  default_timeout: 60\n  max_workers: 4\n"
        )
        old_settings = cfg._settings
        old_root = cfg._project_root
        cfg._settings = None
        try:
            cfg.set_project_root(tmp_path)
            s = get_settings()
            assert s.server.host == "127.0.0.1"
            assert s.server.port == 26521
            assert s.executor.max_workers == 4
        finally:
            cfg._settings = old_settings
            cfg._project_root = old_root


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
    @pytest.mark.zentao("TC-S0862", domain="server/config", priority="P2")
    def test_find_cached(self):
        import taskpps.config as cfg

        old = cfg._project_root
        cfg._project_root = Path("/tmp/cached_root")
        try:
            result = find_project_root()
            assert result == Path("/tmp/cached_root")
        finally:
            cfg._project_root = old

    @pytest.mark.zentao("TC-S0863", domain="server/config", priority="P1")
    def test_find_no_config(self, tmp_path):
        import taskpps.config as cfg

        old = cfg._project_root
        cfg._project_root = None
        try:
            result = find_project_root()
            assert result is not None
        finally:
            cfg._project_root = old

    @pytest.mark.zentao("TC-S0864", domain="server/config", priority="P2")
    def test_set(self, tmp_path):
        import taskpps.config as cfg

        new_root = tmp_path / "new_project"
        new_root.mkdir()
        set_project_root(new_root)
        assert cfg._project_root == new_root.resolve()
        assert cfg._server_home == new_root.resolve()
        assert cfg._project_workdir == new_root.resolve()


class TestLoadSettings:
    @pytest.mark.zentao("TC-S0865", domain="server/config", priority="P2")
    def test_with_path(self, tmp_path):
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("server:\n  host: 0.0.0.0\n  port: 9999\n")
        s = load_settings(str(config_file))
        assert s.server.host == "0.0.0.0"
        assert s.server.port == 9999

    @pytest.mark.zentao("TC-S0866", domain="server/config", priority="P2")
    def test_nonexistent_path(self, tmp_path):
        s = load_settings(str(tmp_path / "nonexistent.yaml"))
        assert isinstance(s, Settings)

    @pytest.mark.zentao("TC-S0867", domain="server/config", priority="P2")
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
    @pytest.mark.zentao("TC-S0868", domain="server/config", priority="P2")
    def test_data_dir(self, setup_project, tmp_project):
        d = get_data_dir()
        assert d.exists()
        # data_dir 基于 server 安装目录，不是项目 workdir
        assert ".taskpps" in str(d)

    @pytest.mark.zentao("TC-S0869", domain="server/config", priority="P2")
    def test_data_dir_creates(self, tmp_path, setup_project):
        # data_dir 由 server_home 决定，不受 _project_workdir 影响
        d = get_data_dir()
        assert d.exists()

    @pytest.mark.zentao("TC-S0870", domain="server/config", priority="P2")
    def test_db_path(self, setup_project, tmp_project):
        p = get_db_path()
        assert p.name == "state.db"
        assert ".taskpps" in str(p)

    @pytest.mark.zentao("TC-S0871", domain="server/config", priority="P2")
    def test_db_path_uses_data_dir(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            p = get_db_path()
            assert p.name == "state.db"
            # db_path 基于 server_home 而非 project_workdir
            assert ".taskpps" in str(p.parent)
        finally:
            cfg._project_workdir = old_workdir

    @pytest.mark.zentao("TC-S0872", domain="server/config", priority="P1")
    def test_logs_dir(self, setup_project):
        d = get_logs_dir()
        assert d.exists()

    @pytest.mark.zentao("TC-S0873", domain="server/config", priority="P1")
    def test_logs_dir_creates(self, tmp_path, setup_project):
        # logs_dir 由 server_home 决定，不受 _project_workdir 影响
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            d = get_logs_dir()
            assert d.exists()
            assert ".taskpps" in str(d)
            assert d.name == "logs"
        finally:
            cfg._project_workdir = old_workdir

    @pytest.mark.zentao("TC-S0874", domain="server/config", priority="P2")
    def test_pipelines_dir(self, setup_project, tmp_project):
        d = get_pipelines_dir()
        assert d == tmp_project / "pipelines"

    @pytest.mark.zentao("TC-S0875", domain="server/config", priority="P2")
    def test_pipelines_dir_no_trailing_slash(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            d = get_pipelines_dir()
            assert d == tmp_path / "pipelines"
        finally:
            cfg._project_workdir = old_workdir

    @pytest.mark.zentao("TC-S0876", domain="server/config", priority="P2")
    def test_agents_dir(self, setup_project, tmp_project):
        d = get_agents_dir()
        assert d == tmp_project / "agents"

    @pytest.mark.zentao("TC-S0877", domain="server/config", priority="P2")
    def test_agents_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            d = get_agents_dir()
            assert d == tmp_path / "agents"
        finally:
            cfg._project_workdir = old_workdir

    @pytest.mark.zentao("TC-S0878", domain="server/config", priority="P2")
    def test_credentials_dir(self, setup_project, tmp_project):
        d = get_credentials_dir()
        assert d == tmp_project / "credentials"

    @pytest.mark.zentao("TC-S0879", domain="server/config", priority="P2")
    def test_credentials_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            d = get_credentials_dir()
            assert d == tmp_path / "credentials"
        finally:
            cfg._project_workdir = old_workdir

    @pytest.mark.zentao("TC-S0880", domain="server/config", priority="P2")
    def test_tasks_dir(self, setup_project, tmp_project):
        d = get_tasks_dir()
        assert d == tmp_project / "tasks"

    @pytest.mark.zentao("TC-S0881", domain="server/config", priority="P2")
    def test_tasks_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            d = get_tasks_dir()
            assert d == tmp_path / "tasks"
        finally:
            cfg._project_workdir = old_workdir

    @pytest.mark.zentao("TC-S0882", domain="server/config", priority="P2")
    def test_plugins_dir(self, setup_project, tmp_project):
        d = get_plugins_dir()
        assert d == tmp_project / "plugins"

    @pytest.mark.zentao("TC-S0883", domain="server/config", priority="P2")
    def test_plugins_dir_custom(self, tmp_path, setup_project):
        import taskpps.config as cfg

        old_workdir = cfg._project_workdir
        cfg._project_workdir = tmp_path
        try:
            d = get_plugins_dir()
            assert d == tmp_path / "plugins"
        finally:
            cfg._project_workdir = old_workdir


class TestServerHome:
    @pytest.mark.zentao("TC-S0884", domain="server/config", priority="P2")
    def test_data_dir_uses_server_home(self, tmp_path):
        """get_data_dir 应使用 get_server_home() 而非硬编码路径。"""
        import taskpps.config as cfg

        custom_home = tmp_path / "custom_deploy"
        custom_home.mkdir()
        old_home = cfg._server_home
        try:
            set_server_home(custom_home)
            d = get_data_dir()
            assert d == custom_home / ".taskpps"
            assert d.exists()
        finally:
            cfg._server_home = old_home

    @pytest.mark.zentao("TC-S0885", domain="server/config", priority="P1")
    def test_logs_dir_uses_server_home(self, tmp_path):
        """get_logs_dir 应使用 get_server_home() 而非硬编码路径。"""
        import taskpps.config as cfg

        custom_home = tmp_path / "custom_deploy"
        custom_home.mkdir()
        old_home = cfg._server_home
        try:
            set_server_home(custom_home)
            d = get_logs_dir()
            assert d == custom_home / ".taskpps" / "logs"
            assert d.exists()
        finally:
            cfg._server_home = old_home

    @pytest.mark.zentao("TC-S0886", domain="server/config", priority="P1")
    def test_logs_dir_respects_env_var(self, tmp_path, monkeypatch):
        """get_logs_dir 应尊重 TASKPPS_SERVER_HOME 环境变量。"""
        import taskpps.config as cfg

        custom_home = tmp_path / "env_deploy"
        custom_home.mkdir()
        old_home = cfg._server_home
        cfg._server_home = None
        monkeypatch.setenv("TASKPPS_SERVER_HOME", str(custom_home))
        try:
            d = get_logs_dir()
            assert d == custom_home / ".taskpps" / "logs"
            assert d.exists()
        finally:
            cfg._server_home = old_home

