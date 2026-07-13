from __future__ import annotations

import pytest

from taskpps.loaders.pipeline_loader import PipelineLoader


class TestParseDict:
    @pytest.mark.zentao("TC-ISSUE189", domain="server/loaders", priority="P0")
    def test_parse_dict_same_as_load(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        yaml_content = (
            "name: test_pipe\n"
            "options:\n"
            "  env:\n"
            "    KEY: ${MY_VAR}\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo ${MY_VAR}\n"
            "  - name: step2\n"
            "    command: echo world\n"
            "    depends_on: [step1]\n"
        )
        p = pipelines_dir / "test.yaml"
        p.write_text(yaml_content)

        loader = PipelineLoader(pipelines_dir)
        env = {"MY_VAR": "resolved_value"}

        from_file = loader.load("test.yaml", env=env)
        assert from_file.name == "test_pipe"
        assert from_file.options.env["KEY"] == "resolved_value"
        assert from_file.tasks is not None or from_file.pipelines is not None
        tasks = from_file.tasks if from_file.tasks else from_file.pipelines[0].tasks
        assert tasks[0].command == "echo resolved_value"

        import yaml

        data = yaml.safe_load(yaml_content)
        from_dict = loader.parse_dict(data, env=env)
        assert from_dict.name == "test_pipe"
        assert from_dict.options.env["KEY"] == "resolved_value"
        tasks2 = from_dict.tasks if from_dict.tasks else from_dict.pipelines[0].tasks
        assert tasks2[0].command == "echo resolved_value"

        assert from_file.name == from_dict.name

    @pytest.mark.zentao("TC-ISSUE189", domain="server/loaders", priority="P0")
    def test_parse_dict_no_env(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        yaml_content = (
            "name: simple\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo hello\n"
        )

        loader = PipelineLoader(pipelines_dir)
        import yaml

        data = yaml.safe_load(yaml_content)
        result = loader.parse_dict(data)
        assert result.name == "simple"
        tasks = result.tasks if result.tasks else result.pipelines[0].tasks
        assert len(tasks) == 1
        assert tasks[0].command == "echo hello"

    @pytest.mark.zentao("TC-ISSUE189", domain="server/loaders", priority="P0")
    def test_parse_dict_with_config_env(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()

        data = {
            "name": "config_test",
            "config": {"env": {"DUT_IP": "10.0.0.1"}},
            "tasks": [{"name": "step1", "command": "echo ${env.DUT_IP}"}],
        }

        loader = PipelineLoader(pipelines_dir)
        result = loader.parse_dict(data)
        tasks = result.tasks if result.tasks else result.pipelines[0].tasks
        assert tasks[0].command == "echo 10.0.0.1"

    @pytest.mark.zentao("TC-ISSUE189", domain="server/loaders", priority="P1")
    def test_parse_dict_params_env_overrides_config_env(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()

        data = {
            "name": "priority_test",
            "config": {"env": {"KEY": "config_val"}},
            "tasks": [{"name": "step1", "command": "echo ${env.KEY}"}],
        }

        loader = PipelineLoader(pipelines_dir)
        result = loader.parse_dict(data, env={"KEY": "param_val"})
        tasks = result.tasks if result.tasks else result.pipelines[0].tasks
        assert tasks[0].command == "echo param_val"

    @pytest.mark.zentao("TC-ISSUE189", domain="server/loaders", priority="P1")
    def test_parse_dict_subpipelines(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()

        data = {
            "name": "multi_sub",
            "pipelines": [
                {
                    "name": "build",
                    "tasks": [{"name": "compile", "command": "echo compile"}],
                },
                {
                    "name": "deploy",
                    "depends_on": ["build"],
                    "tasks": [{"name": "upload", "command": "echo upload"}],
                },
            ],
        }

        loader = PipelineLoader(pipelines_dir)
        result = loader.parse_dict(data)
        assert result.name == "multi_sub"
        assert result.pipelines is not None
        assert len(result.pipelines) == 2
        assert result.pipelines[0].name == "build"
        assert result.pipelines[1].name == "deploy"

    @pytest.mark.zentao("TC-ISSUE189", domain="server/loaders", priority="P2")
    def test_parse_dict_consistency_load_reload(self, tmp_path):
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        yaml_content = (
            "name: roundtrip\n"
            "options:\n"
            "  timeout: 120\n"
            "  on_failure: continue\n"
            "tasks:\n"
            "  - name: task-a\n"
            "    command: echo a\n"
        )
        p = pipelines_dir / "roundtrip.yaml"
        p.write_text(yaml_content)

        import yaml

        loader = PipelineLoader(pipelines_dir)
        from_file = loader.load("roundtrip.yaml")
        from_dict = loader.parse_dict(yaml.safe_load(yaml_content))

        assert from_file.model_dump() == from_dict.model_dump()
