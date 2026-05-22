from taskpps.config import get_settings, load_settings, get_data_dir, get_db_path, get_logs_dir, get_pipelines_dir, get_agents_dir, get_credentials_dir, get_tasks_dir, get_plugins_dir


def test_settings_defaults():
    s = get_settings()
    assert s.server.host == "127.0.0.1"
    assert s.server.port == 26521
    assert s.executor.default_timeout == 60
    assert s.executor.max_workers == 4
    assert s.env.get("GLOBAL_VAR") == "global_value"


def test_load_settings_from_file(setup_project):
    s = get_settings()
    assert s.server.host == "127.0.0.1"
    assert s.server.port == 26521
    assert s.executor.max_workers == 4


def test_data_dir(setup_project, tmp_project):
    d = get_data_dir()
    assert d.exists()
    assert str(tmp_project) in str(d)


def test_db_path(setup_project, tmp_project):
    p = get_db_path()
    assert p.name == "state.db"
    assert ".taskpps" in str(p)


def test_logs_dir(setup_project):
    d = get_logs_dir()
    assert d.exists()


def test_pipelines_dir(setup_project, tmp_project):
    d = get_pipelines_dir()
    assert d == tmp_project / "pipelines"


def test_agents_dir(setup_project, tmp_project):
    d = get_agents_dir()
    assert d == tmp_project / "agents"


def test_credentials_dir(setup_project, tmp_project):
    d = get_credentials_dir()
    assert d == tmp_project / "credentials"


def test_tasks_dir(setup_project, tmp_project):
    d = get_tasks_dir()
    assert d == tmp_project / "tasks"


def test_plugins_dir(setup_project, tmp_project):
    d = get_plugins_dir()
    assert d == tmp_project / "plugins"
