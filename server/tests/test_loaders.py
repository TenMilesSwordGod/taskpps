import logging

import pytest

from taskpps.loaders.agent_loader import AgentLoader
from taskpps.loaders.credential_loader import CredentialLoader
from taskpps.loaders.pipeline_loader import PipelineLoader, substitute_env_vars


class TestPipelineLoader:
    def test_load(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        spec = loader.load("deploy.yaml")
        assert spec.name == "deploy"
        assert len(spec.tasks) == 2
        assert spec.tasks[0].name == "step1"
        assert spec.tasks[1].depends_on == ["step1"]

    def test_load_with_pipelines_prefix(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        spec = loader.load("pipelines/deploy.yaml")
        assert spec.name == "deploy"
        assert len(spec.tasks) == 2

        spec2 = loader.load("pipelines/simple.yaml")
        assert spec2.name == "simple"

    def test_load_prefix_with_subdir(self, setup_project, tmp_project):
        subdir = tmp_project / "pipelines" / "nested"
        subdir.mkdir()
        nested_yaml = subdir / "inner.yaml"
        nested_yaml.write_text("name: inner\noptions: {}\ntasks:\n  - name: t1\n    command: echo nested\n")
        try:
            loader = PipelineLoader(tmp_project / "pipelines")
            spec = loader.load("pipelines/nested/inner.yaml")
            assert spec.name == "inner"
            assert spec.tasks[0].name == "t1"
        finally:
            nested_yaml.unlink()
            subdir.rmdir()

    def test_load_all(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        all_pipelines = loader.load_all()
        assert "deploy" in all_pipelines
        assert "simple" in all_pipelines

    def test_not_found(self, setup_project, tmp_project):
        loader = PipelineLoader(tmp_project / "pipelines")
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent.yaml")

    def test_empty_file(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        empty_file = pipelines_dir / "empty.yaml"
        empty_file.write_text("")
        loader = PipelineLoader(pipelines_dir)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty.yaml")

    def test_load_all_no_dir(self, tmp_path):
        loader = PipelineLoader(tmp_path / "nonexistent")
        result = loader.load_all()
        assert result == {}

    def test_load_with_env_subst(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        p = pipelines_dir / "env_test.yaml"
        p.write_text(
            "name: env_test\noptions:\n  env:\n    KEY: ${MY_VAR}\ntasks:\n  - name: step1\n    command: echo ${MY_VAR}\n"
        )
        loader = PipelineLoader(pipelines_dir)
        spec = loader.load("env_test.yaml", env={"MY_VAR": "resolved_value"})
        assert spec.options.env["KEY"] == "resolved_value"
        assert spec.tasks[0].command == "echo resolved_value"

    def test_load_absolute_path(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir(parents=True, exist_ok=True)
        yaml_file = pipelines_dir / "absolute.yaml"
        yaml_file.write_text("name: absolute\noptions: {}\ntasks:\n  - name: t1\n    command: echo abs\n")
        loader = PipelineLoader(pipelines_dir)
        spec = loader.load("absolute.yaml")
        assert spec.name == "absolute"

    def test_load_all_includes_yml(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        yml_file = pipelines_dir / "test.yml"
        yml_file.write_text("name: yml_test\noptions: {}\ntasks:\n  - name: t1\n    command: echo yml\n")
        loader = PipelineLoader(pipelines_dir)
        result = loader.load_all()
        assert "yml_test" in result


class TestAgentLoader:
    def test_load(self, setup_project, tmp_project):
        loader = AgentLoader(tmp_project / "agents")
        data = loader.load("staging-server")
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 22
        assert data["username"] == "test"

    def test_not_found(self, setup_project, tmp_project):
        loader = AgentLoader(tmp_project / "agents")
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    def test_load_all(self, setup_project, tmp_project):
        loader = AgentLoader(tmp_project / "agents")
        all_agents = loader.load_all()
        assert "staging-server" in all_agents

    def test_load_all_no_dir(self, tmp_path):
        loader = AgentLoader(tmp_path / "nonexistent")
        result = loader.load_all()
        assert result == {}

    def test_load_all_includes_yml(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        yml_file = agents_dir / "test-agent.yml"
        yml_file.write_text("host: 1.2.3.4\nport: 22\nusername: test\n")
        loader = AgentLoader(agents_dir)
        result = loader.load_all()
        assert "test-agent" in result

    def test_empty_yaml(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        empty_file = agents_dir / "empty.yaml"
        empty_file.write_text("")
        loader = AgentLoader(agents_dir)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty")

    def test_load_all_with_exception(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        bad_file = agents_dir / "bad.yaml"
        bad_file.write_text("{invalid: yaml: : }")
        loader = AgentLoader(agents_dir)
        result = loader.load_all()
        assert result == {}

    def test_load_yml_extension(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        yml_file = agents_dir / "test-agent.yml"
        yml_file.write_text("host: 5.6.7.8\nport: 2222\nusername: test\n")
        loader = AgentLoader(agents_dir)
        data = loader.load("test-agent")
        assert data["host"] == "5.6.7.8"


class TestCredentialLoader:
    def test_load(self, setup_project, tmp_project):
        loader = CredentialLoader(tmp_project / "credentials")
        data = loader.load("default-cred")
        assert data["password"] == "testpass"

    def test_not_found(self, setup_project, tmp_project):
        loader = CredentialLoader(tmp_project / "credentials")
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent")

    def test_load_all_no_dir(self, tmp_path):
        loader = CredentialLoader(tmp_path / "nonexistent")
        result = loader.load_all()
        assert result == {}

    def test_load_all_includes_yml(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "test-cred.yml"
        yml_file.write_text("password: testpass\n")
        loader = CredentialLoader(creds_dir)
        result = loader.load_all()
        assert "test-cred" in result

    def test_empty_yaml(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        empty_file = creds_dir / "empty.yaml"
        empty_file.write_text("")
        loader = CredentialLoader(creds_dir)
        with pytest.raises(ValueError, match="empty"):
            loader.load("empty")

    def test_load_all_with_exception(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        bad_file = creds_dir / "bad.yaml"
        bad_file.write_text("{invalid: yaml: : }")
        loader = CredentialLoader(creds_dir)
        result = loader.load_all()
        assert result == {}

    def test_load_yml_extension(self, tmp_path):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "test-cred.yml"
        yml_file.write_text("password: secret\n")
        loader = CredentialLoader(creds_dir)
        data = loader.load("test-cred")
        assert data["password"] == "secret"

    def test_password_warning(self, tmp_path, caplog):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "test-cred.yaml"
        yml_file.write_text("password: changeme\n")
        loader = CredentialLoader(creds_dir)
        with caplog.at_level(logging.WARNING):
            data = loader.load("test-cred")
        assert data["password"] == "changeme"
        assert "plaintext password" in caplog.text

    def test_key_path_no_warning(self, tmp_path, caplog):
        creds_dir = tmp_path / "credentials"
        creds_dir.mkdir()
        yml_file = creds_dir / "key-cred.yaml"
        yml_file.write_text("key_path: ~/.ssh/deploy_key\n")
        loader = CredentialLoader(creds_dir)
        with caplog.at_level(logging.WARNING):
            data = loader.load("key-cred")
        assert data["key_path"] == "~/.ssh/deploy_key"
        assert "plaintext password" not in caplog.text


class TestSubstituteEnvVars:
    def test_simple(self):
        env = {"APP_ENV": "production", "TAG": "v1.0"}
        result = substitute_env_vars("echo ${APP_ENV} ${TAG}", env)
        assert result == "echo production v1.0"

    def test_missing(self):
        env = {}
        result = substitute_env_vars("echo ${MISSING}", env)
        assert result == "echo ${MISSING}"

    def test_dict(self):
        env = {"KEY": "val"}
        data = {"command": "echo ${KEY}", "nested": {"val": "${KEY}"}}
        result = substitute_env_vars(data, env)
        assert result["command"] == "echo val"
        assert result["nested"]["val"] == "val"

    def test_list(self):
        env = {"X": "1"}
        data = ["${X}", "static"]
        result = substitute_env_vars(data, env)
        assert result == ["1", "static"]

    def test_no_match(self):
        result = substitute_env_vars("no vars here", {})
        assert result == "no vars here"

    def test_int(self):
        result = substitute_env_vars(42, {})
        assert result == 42

    def test_env_prefix(self):
        env = {"DUT_IP": "192.168.1.100"}
        result = substitute_env_vars("echo ${env.DUT_IP}", env)
        assert result == "echo 192.168.1.100"

    def test_env_prefix_missing(self):
        result = substitute_env_vars("echo ${env.MISSING}", {})
        assert result == "echo ${env.MISSING}"

    def test_load_with_env_prefix_and_no_env_param(self, tmp_path, monkeypatch):
        # 测试没有显式传入 env 参数时，仍然可以通过 settings.env 和 os.environ 替换
        monkeypatch.setenv("SYS_ENV", "sys_value")
        
        # 模拟 settings.env
        import taskpps.config
        from taskpps.config import Settings
        original_settings = taskpps.config._settings
        try:
            taskpps.config._settings = Settings(env={"SETTINGS_ENV": "settings_value"})
            
            pipelines_dir = tmp_path / "pipelines"
            pipelines_dir.mkdir()
            p = pipelines_dir / "env_prefix_test.yaml"
            p.write_text("""name: env_prefix_test
tasks:
  - name: step1
    command: echo ${env.SYS_ENV} ${env.SETTINGS_ENV} ${env.MISSING}
""")
            loader = PipelineLoader(pipelines_dir)
            # 没有传入 env 参数！
            spec = loader.load("env_prefix_test.yaml")
            assert spec.tasks[0].command == "echo sys_value settings_value ${env.MISSING}"
        finally:
            taskpps.config._settings = original_settings

    def test_load_with_env_prefix_and_params(self, tmp_path, monkeypatch):
        # 测试传入 env 参数时的优先级
        monkeypatch.setenv("SYS_ENV", "sys_value")
        
        # 模拟 settings.env
        import taskpps.config
        from taskpps.config import Settings
        original_settings = taskpps.config._settings
        try:
            taskpps.config._settings = Settings(env={"SETTINGS_ENV": "settings_value", "OVERLAPPED": "settings_val"})
            
            pipelines_dir = tmp_path / "pipelines"
            pipelines_dir.mkdir()
            p = pipelines_dir / "env_priority_test.yaml"
            p.write_text("""name: env_priority_test
tasks:
  - name: step1
    command: echo ${env.PARAM_ENV} ${env.SETTINGS_ENV} ${env.SYS_ENV} ${env.OVERLAPPED}
""")
            loader = PipelineLoader(pipelines_dir)
            # 传入 env 参数，包含与 settings.env 重叠的变量
            spec = loader.load("env_priority_test.yaml", env={
                "PARAM_ENV": "param_value",
                "OVERLAPPED": "param_val"
            })
            # 优先级：传入的 env > settings.env > os.environ
            assert spec.tasks[0].command == "echo param_value settings_value sys_value param_val"
        finally:
            taskpps.config._settings = original_settings

    def test_load_always_substitute_vars(self, tmp_path, monkeypatch):
        # 测试即使没有 env 参数，也会执行变量替换
        monkeypatch.setenv("TEST_VAR", "os_value")
        
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        p = pipelines_dir / "always_substitute.yaml"
        p.write_text("""name: always_substitute
tasks:
  - name: step1
    command: echo ${TEST_VAR}
""")
        loader = PipelineLoader(pipelines_dir)
        # 没有传入 env 参数
        spec = loader.load("always_substitute.yaml")
        assert spec.tasks[0].command == "echo os_value"

    def test_no_env_prefix_also_uses_settings_and_os(self, tmp_path, monkeypatch):
        # 测试没有 env. 前缀的变量也会按同样的优先级查找
        monkeypatch.setenv("SYS_NO_PREFIX", "sys_no_prefix")
        
        # 模拟 settings.env
        import taskpps.config
        from taskpps.config import Settings
        original_settings = taskpps.config._settings
        try:
            taskpps.config._settings = Settings(env={"SETTINGS_NO_PREFIX": "settings_no_prefix", "OVERLAP_NO_PREFIX": "settings_np"})
            
            pipelines_dir = tmp_path / "pipelines"
            pipelines_dir.mkdir()
            p = pipelines_dir / "no_prefix_test.yaml"
            p.write_text("""name: no_prefix_test
tasks:
  - name: step1
    command: echo ${PARAM_NO_PREFIX} ${SETTINGS_NO_PREFIX} ${SYS_NO_PREFIX} ${OVERLAP_NO_PREFIX}
""")
            loader = PipelineLoader(pipelines_dir)
            spec = loader.load("no_prefix_test.yaml", env={
                "PARAM_NO_PREFIX": "param_no_prefix",
                "OVERLAP_NO_PREFIX": "param_np"
            })
            assert spec.tasks[0].command == "echo param_no_prefix settings_no_prefix sys_no_prefix param_np"
        finally:
            taskpps.config._settings = original_settings