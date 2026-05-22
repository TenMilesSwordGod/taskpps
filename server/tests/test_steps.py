import pytest
from taskpps.schemas.pipeline import TaskYAML, TaskStep, OptionsYAML, PipelineYAML
from taskpps.domain.pipeline import ResolvedTask, ResolvedStep
from taskpps.executors import create_executor
from taskpps.executors.local import LocalExecutor


class TestTaskStepSchema:
    def test_task_step_basic(self):
        step = TaskStep(run="echo hello")
        assert step.run == "echo hello"
        assert step.cd is None
        assert step.env == {}

    def test_task_step_with_cd(self):
        step = TaskStep(run="ls", cd="/tmp")
        assert step.cd == "/tmp"

    def test_task_step_with_env(self):
        step = TaskStep(run="echo $FOO", env={"FOO": "bar"})
        assert step.env == {"FOO": "bar"}

    def test_task_step_full(self):
        step = TaskStep(run="make build", cd="/app", env={"APP_ENV": "prod"})
        assert step.run == "make build"
        assert step.cd == "/app"
        assert step.env == {"APP_ENV": "prod"}


class TestTaskYAMLSteps:
    def test_task_yaml_steps_type(self):
        task = TaskYAML(
            name="deploy",
            steps=[
                TaskStep(run="echo step1"),
                TaskStep(run="echo step2", cd="/tmp"),
            ],
        )
        assert task.get_task_type() == "steps"

    def test_task_yaml_command_type_still_works(self):
        task = TaskYAML(name="build", command="make build")
        assert task.get_task_type() == "command"

    def test_task_yaml_invoke_type_still_works(self):
        task = TaskYAML(
            name="migrate",
            invoke={"task": "deploy_tasks.migrate_db"},
        )
        assert task.get_task_type() == "invoke"

    def test_task_yaml_with_cwd(self):
        task = TaskYAML(name="build", command="make", cwd="/app")
        assert task.cwd == "/app"

    def test_task_yaml_steps_with_cwd(self):
        task = TaskYAML(
            name="deploy",
            cwd="/app",
            steps=[
                TaskStep(run="make build"),
                TaskStep(run="make deploy", cd="/deploy"),
            ],
        )
        assert task.cwd == "/app"
        assert task.steps[1].cd == "/deploy"


class TestResolvedStep:
    def test_resolved_step_from_yaml(self):
        step_yaml = TaskStep(run="ls -la", cd="/tmp", env={"FOO": "bar"})
        resolved = ResolvedStep.from_yaml(step_yaml)
        assert resolved.run == "ls -la"
        assert resolved.cd == "/tmp"
        assert resolved.env == {"FOO": "bar"}

    def test_resolved_step_defaults(self):
        step_yaml = TaskStep(run="echo hello")
        resolved = ResolvedStep.from_yaml(step_yaml)
        assert resolved.cd is None
        assert resolved.env == {}


class TestResolvedTaskSteps:
    def test_resolved_task_with_steps(self):
        task_yaml = TaskYAML(
            name="deploy",
            cwd="/app",
            steps=[
                TaskStep(run="make build"),
                TaskStep(run="make deploy", cd="/deploy"),
                TaskStep(run="systemctl restart app", env={"APP_ENV": "prod"}),
            ],
        )
        options = OptionsYAML()
        resolved = ResolvedTask.from_yaml(task_yaml, options)

        assert resolved.task_type == "steps"
        assert resolved.cwd == "/app"
        assert len(resolved.steps) == 3
        assert resolved.steps[0].run == "make build"
        assert resolved.steps[0].cd is None
        assert resolved.steps[1].cd == "/deploy"
        assert resolved.steps[2].env == {"APP_ENV": "prod"}

    def test_resolved_task_steps_inherit_options_env(self):
        task_yaml = TaskYAML(
            name="deploy",
            steps=[TaskStep(run="echo hello")],
        )
        options = OptionsYAML(env={"GLOBAL": "value"})
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.env == {"GLOBAL": "value"}

    def test_resolved_task_command_with_cwd(self):
        task_yaml = TaskYAML(name="build", command="make", cwd="/app")
        options = OptionsYAML()
        resolved = ResolvedTask.from_yaml(task_yaml, options)
        assert resolved.task_type == "command"
        assert resolved.cwd == "/app"


class TestPipelineYAMLSteps:
    def test_pipeline_yaml_with_steps(self):
        pipeline_yaml = PipelineYAML(
            name="deploy-steps",
            options=OptionsYAML(env={"APP_ENV": "staging"}),
            tasks=[
                TaskYAML(
                    name="build-and-deploy",
                    cwd="/app",
                    steps=[
                        TaskStep(run="make build"),
                        TaskStep(run="make deploy"),
                        TaskStep(run="systemctl restart app"),
                    ],
                    timeout=300,
                ),
                TaskYAML(
                    name="verify",
                    steps=[
                        TaskStep(run="curl -sf http://localhost:8000/health"),
                        TaskStep(run="tail -20 /var/log/app.log", cd="/var/log"),
                    ],
                    depends_on=["build-and-deploy"],
                ),
            ],
        )
        assert len(pipeline_yaml.tasks) == 2
        assert pipeline_yaml.tasks[0].get_task_type() == "steps"
        assert len(pipeline_yaml.tasks[0].steps) == 3
        assert pipeline_yaml.tasks[1].steps[1].cd == "/var/log"


class TestCreateExecutorSteps:
    def test_create_executor_steps_type_local(self):
        task = ResolvedTask(
            name="deploy",
            task_type="steps",
            steps=[ResolvedStep(run="echo hello")],
        )
        executor = create_executor(task)
        assert isinstance(executor, LocalExecutor)

    def test_create_executor_steps_type_ssh(self):
        task = ResolvedTask(
            name="deploy",
            task_type="steps",
            steps=[ResolvedStep(run="echo hello")],
            host="myhost",
        )
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            from pathlib import Path
            agents_dir = Path(tmp_dir) / "agents"
            agents_dir.mkdir()
            agent_file = agents_dir / "myhost.yaml"
            agent_file.write_text("host: 1.2.3.4\nport: 22\nusername: root\n")
            with patch("taskpps.loaders.agent_loader.get_agents_dir", return_value=agents_dir):
                executor = create_executor(task)
                from taskpps.executors.ssh import SSHExecutor
                assert isinstance(executor, SSHExecutor)
