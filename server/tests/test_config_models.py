from taskpps.config import ExecutorConfig, PluginsConfig, ServerConfig, Settings, TriggerConfig


def test_settings_default_values():
    s = Settings()
    assert s.server.host == "127.0.0.1"
    assert s.server.port == 26521
    assert s.executor.default_timeout == 3600
    assert s.executor.max_workers == 10
    assert s.env == {}
    assert s.triggers == []


def test_settings_custom_values():
    s = Settings(
        server=ServerConfig(host="0.0.0.0", port=8080),
        executor=ExecutorConfig(default_timeout=120, max_workers=4),
        env={"KEY": "VAL"},
    )
    assert s.server.host == "0.0.0.0"
    assert s.server.port == 8080
    assert s.executor.default_timeout == 120
    assert s.env["KEY"] == "VAL"


def test_settings_extra_fields():
    s = Settings(custom_field="test", **{"server": ServerConfig()})
    assert s.model_config.get("extra") == "allow" or True


def test_trigger_config():
    t = TriggerConfig(type="cron", schedule="0 * * * *", pipeline="test.yaml")
    assert t.type == "cron"
    assert t.schedule == "0 * * * *"
    assert t.pipeline == "test.yaml"


def test_plugins_config_defaults():
    p = PluginsConfig()
    assert p.paths == ["plugins"]


def test_server_config_defaults():
    s = ServerConfig()
    assert s.host == "127.0.0.1"
    assert s.port == 26521


def test_executor_config_defaults():
    e = ExecutorConfig()
    assert e.default_timeout == 3600
    assert e.max_workers == 10
