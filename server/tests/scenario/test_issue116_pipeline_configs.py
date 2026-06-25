"""Issue #116: verify all pipeline configuration possibilities.

Covers:
- sequential execution + host/cwd config
- different host configs
- parallel execution
- multi-subpipeline (steps + parallel mixed)
- on_failure: continue behavior
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import (
    ResolvedPipeline,
    ResolvedStep,
    ResolvedSubPipeline,
    ResolvedTask,
)
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import PipelineConfig, PipelineYAML


def _setup_config():
    import taskpps.config as cfg

    if cfg._project_root is None:
        root = cfg.find_project_root()
        cfg.set_project_root(root)
    cfg._settings = None
    cfg.load_settings()


# -- YAML parsing tests ------------------------------------------


class TestYAMLParsing:
    """Verify YAML configs from issue #116 parse correctly."""

    @pytest.mark.zentao("TC-S0136", domain="server/scenario", priority="P1")
    def test_test01_sequential_with_host_and_cwd(self):
        yaml_str = """
name: Test 01
config:
    host: auto-03
    timeout: 86400
    on_failure: continue
    execution_strategy: sequential
pipelines:
    - name: Sync Automation code
      config:
        cwd: /home/auto/heng/
      tasks:
          - name: step1
            command: echo step1
          - name: step2
            command: echo step2
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        assert spec.name == "Test 01"
        config = spec.get_effective_config()
        assert config.host == "auto-03"
        assert config.timeout == 86400
        assert config.on_failure == "continue"
        assert config.execution_strategy == "sequential"

        sub = spec.pipelines[0]
        assert sub.name == "Sync Automation code"
        assert sub.config is not None
        assert sub.config.cwd == "/home/auto/heng/"
        assert len(sub.tasks) == 2
        assert sub.tasks[0].name == "step1"
        assert sub.tasks[0].command == "echo step1"

    @pytest.mark.zentao("TC-S0137", domain="server/scenario", priority="P1")
    def test_test01_cwd_at_subpipeline_level_ignored(self):
        """cwd at subpipeline level (without config:) is silently ignored."""
        yaml_str = """
name: Test 01
config:
    host: auto-03
pipelines:
    - name: Sync Automation code
      cwd: /home/auto/heng/
      tasks:
          - name: step1
            command: echo step1
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        sub = spec.pipelines[0]
        # cwd at subpipeline level is not parsed, config is None
        assert sub.config is None

    @pytest.mark.zentao("TC-S0138", domain="server/scenario", priority="P1")
    def test_test02_sequential_with_cwd(self):
        yaml_str = """
name: Test 02
config:
    host: auto-03
    timeout: 86400
    on_failure: continue
    execution_strategy: sequential
pipelines:
    - name: Sync Automation code
      config:
        cwd: /home/auto/heng/
      tasks:
          - name: step3
            command: echo step3
          - name: step4
            command: echo step4
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        config = spec.get_effective_config()
        assert config.host == "auto-03"
        assert spec.pipelines[0].config is not None
        assert spec.pipelines[0].config.cwd == "/home/auto/heng/"

    @pytest.mark.zentao("TC-S0139", domain="server/scenario", priority="P1")
    def test_test03_sequential_no_cwd(self):
        yaml_str = """
name: Test 03
config:
    host: auto-cts
    timeout: 86400
    on_failure: continue
    execution_strategy: sequential
pipelines:
    - name: Sync Automation code
      tasks:
          - name: step3
            command: echo step3
          - name: step4
            command: echo step4
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        config = spec.get_effective_config()
        assert config.host == "auto-cts"
        assert spec.pipelines[0].config is None or spec.pipelines[0].config.cwd is None

    @pytest.mark.zentao("TC-S0140", domain="server/scenario", priority="P1")
    def test_test04_parallel(self):
        yaml_str = """
name: Test 04 parallel
config:
    host: auto-cts
    timeout: 86400
    on_failure: continue
    execution_strategy: parallel
pipelines:
    - name: Sync Automation code
      tasks:
          - name: step3
            command: echo step3
          - name: step4
            command: echo step4
          - name: step5
            command: echo step5
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        config = spec.get_effective_config()
        assert config.execution_strategy == "parallel"
        assert len(spec.pipelines[0].tasks) == 3

    @pytest.mark.zentao("TC-S0141", domain="server/scenario", priority="P1")
    def test_test04_multisub_with_steps_and_parallel(self):
        yaml_str = """
name: Test 04 multi-sub
config:
    host: auto-cts
    timeout: 86400
    on_failure: continue
    execution_strategy: sequential
pipelines:
    - name: setup
      tasks:
          - name: fry
            steps:
                - cd: /tmp
                  run: ls
                - cd: /home
                  run: pwd
                - cd: /
                  run: pwd
                - run: echo done
    - name: Sync Automation code
      config:
        execution_strategy: parallel
      tasks:
          - name: step3
            command: echo step3
          - name: step4
            command: echo step4
          - name: step5
            command: echo step5
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        assert len(spec.pipelines) == 2
        setup_sub = spec.pipelines[0]
        assert setup_sub.name == "setup"
        fry_task = setup_sub.tasks[0]
        assert fry_task.name == "fry"
        assert fry_task.steps is not None
        assert len(fry_task.steps) == 4
        assert fry_task.steps[0].cd == "/tmp"
        assert fry_task.steps[0].run == "ls"
        assert fry_task.steps[3].run == "echo done"

        sync_sub = spec.pipelines[1]
        assert sync_sub.name == "Sync Automation code"
        assert sync_sub.config is not None
        assert sync_sub.config.execution_strategy == "parallel"
        assert len(sync_sub.tasks) == 3

    @pytest.mark.zentao("TC-S0142", domain="server/scenario", priority="P2")
    def test_test04_execution_strategy_at_subpipeline_level_ignored(self):
        """execution_strategy at subpipeline level (without config:) is ignored."""
        yaml_str = """
name: Test 04
config:
    host: auto-cts
pipelines:
    - name: Sync Automation code
      execution_strategy: parallel
      tasks:
          - name: step3
            command: echo step3
"""
        data = yaml.safe_load(yaml_str)
        spec = PipelineYAML(**data)

        sub = spec.pipelines[0]
        assert sub.config is None


# -- execution tests (mock executor) ----------------------------


class TestIssue116Execution:
    """Verify various pipeline configs execute correctly (mock executor)."""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0143", domain="server/scenario", priority="P1")
    async def test_sequential_execution_order(self, db_engine, clean_db):
        _setup_config()
        task1 = ResolvedTask(name="step1", task_type="command", command="echo step1")
        task2 = ResolvedTask(name="step2", task_type="command", command="echo step2")
        sub = ResolvedSubPipeline(
            name="Sync Automation code",
            config=PipelineConfig(host="auto-03", cwd="/home/auto/heng/"),
            tasks=[task1, task2],
        )
        pipeline = ResolvedPipeline(name="Test01", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="test01")
        runner = PipelineRunner(run_id="test01", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"Sync Automation code.step1": "tr1", "Sync Automation code.step2": "tr2"}

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            executed.append(command)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed == ["echo step1", "echo step2"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0144", domain="server/scenario", priority="P1")
    async def test_cwd_passed_to_executor(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(name="t1", task_type="command", command="pwd", cwd="/home/auto/heng/")
        sub = ResolvedSubPipeline(name="sub", config=PipelineConfig(), tasks=[task])
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cwd-test")
        runner = PipelineRunner(run_id="cwd-test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.t1": "tr1"}

        captured_cwd = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            captured_cwd.append(cwd)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert captured_cwd == ["/home/auto/heng/"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0145", domain="server/scenario", priority="P1")
    async def test_host_from_config_applied(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(name="t1", task_type="command", command="echo hi", host="auto-cts")
        sub = ResolvedSubPipeline(name="sub", config=PipelineConfig(), tasks=[task])
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="host-test")
        runner = PipelineRunner(run_id="host-test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.t1": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0)

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        mock_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0146", domain="server/scenario", priority="P1")
    async def test_parallel_execution(self, db_engine, clean_db):
        _setup_config()
        tasks = [
            ResolvedTask(name="step3", task_type="command", command="echo s3"),
            ResolvedTask(name="step4", task_type="command", command="echo s4"),
            ResolvedTask(name="step5", task_type="command", command="echo s5"),
        ]
        sub = ResolvedSubPipeline(
            name="Sync Automation code",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="Test04p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="test04p")
        runner = PipelineRunner(run_id="test04p", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "Sync Automation code.step3": "tr3",
            "Sync Automation code.step4": "tr4",
            "Sync Automation code.step5": "tr5",
        }

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            executed.append(command)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed) == 3
        assert set(executed) == {"echo s3", "echo s4", "echo s5"}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0147", domain="server/scenario", priority="P2")
    async def test_steps_with_cd(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="fry",
            task_type="steps",
            steps=[
                ResolvedStep(run="ls", cd="/tmp"),
                ResolvedStep(run="pwd", cd="/home"),
                ResolvedStep(run="pwd", cd="/"),
                ResolvedStep(run="echo done"),
            ],
        )
        sub = ResolvedSubPipeline(name="setup", config=PipelineConfig(), tasks=[task])
        pipeline = ResolvedPipeline(name="Test04m", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="test04m")
        runner = PipelineRunner(run_id="test04m", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"setup.fry": "tr-fry"}

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            executed.append((command, cwd))
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed == [
            ("ls", "/tmp"),
            ("pwd", "/home"),
            ("pwd", "/"),
            ("echo done", None),
        ]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0148", domain="server/scenario", priority="P1")
    async def test_multi_subpipeline_sequential_outer(self, db_engine, clean_db):
        _setup_config()
        setup_task = ResolvedTask(
            name="fry",
            task_type="steps",
            steps=[ResolvedStep(run="echo setup-done")],
        )
        setup_sub = ResolvedSubPipeline(name="setup", config=PipelineConfig(), tasks=[setup_task])

        parallel_tasks = [
            ResolvedTask(name="step3", task_type="command", command="echo s3"),
            ResolvedTask(name="step4", task_type="command", command="echo s4"),
            ResolvedTask(name="step5", task_type="command", command="echo s5"),
        ]
        parallel_sub = ResolvedSubPipeline(
            name="Sync Automation code",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=parallel_tasks,
        )

        pipeline = ResolvedPipeline(
            name="Test04m",
            subpipelines=[setup_sub, parallel_sub],
            top_config=PipelineConfig(execution_strategy="sequential"),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="test04m-full")
        runner = PipelineRunner(run_id="test04m-full", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "setup.fry": "tr-fry",
            "Sync Automation code.step3": "tr3",
            "Sync Automation code.step4": "tr4",
            "Sync Automation code.step5": "tr5",
        }

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            executed.append(command)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed) == 4
        assert executed[0] == "echo setup-done"
        assert set(executed[1:]) == {"echo s3", "echo s4", "echo s5"}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0149", domain="server/scenario", priority="P0")
    async def test_on_failure_continue_parallel_independent_runs(self, db_engine, clean_db):
        """on_failure=continue + parallel: failed task does not block independent task."""
        _setup_config()
        tasks = [
            ResolvedTask(name="fail-task", task_type="command", command="exit 1"),
            ResolvedTask(name="independent", task_type="command", command="echo ok"),
        ]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(on_failure="continue", execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cont-test")
        runner = PipelineRunner(run_id="cont-test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.fail-task": "tr1", "sub.independent": "tr2"}

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            if command == "exit 1":
                return ExecutorResult(exit_code=1, stderr="fail")
            executed.append(command)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "echo ok" in executed

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0150", domain="server/scenario", priority="P0")
    async def test_on_failure_continue_with_depends_on_still_runs(self, db_engine, clean_db):
        """on_failure=continue: task with depends_on still runs even if dependency failed."""
        _setup_config()
        tasks = [
            ResolvedTask(name="fail-task", task_type="command", command="exit 1"),
            ResolvedTask(
                name="downstream",
                task_type="command",
                command="echo runs-anyway",
                depends_on=["fail-task"],
            ),
        ]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(on_failure="continue"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cont-dep")
        runner = PipelineRunner(run_id="cont-dep", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub.fail-task": "tr1",
            "sub.downstream": "tr2",
        }

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            if command == "exit 1":
                return ExecutorResult(exit_code=1, stderr="fail")
            executed.append(command)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "echo runs-anyway" in executed

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0151", domain="server/scenario", priority="P0")
    async def test_on_failure_fail_with_depends_on_skips(self, db_engine, clean_db):
        """on_failure=fail: task with depends_on is skipped when dependency failed."""
        _setup_config()
        tasks = [
            ResolvedTask(name="fail-task", task_type="command", command="exit 1"),
            ResolvedTask(
                name="downstream",
                task_type="command",
                command="echo should-skip",
                depends_on=["fail-task"],
            ),
        ]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(on_failure="fail"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="fail-dep")
        runner = PipelineRunner(run_id="fail-dep", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub.fail-task": "tr1",
            "sub.downstream": "tr2",
        }

        executed = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            if command == "exit 1":
                return ExecutorResult(exit_code=1, stderr="fail")
            executed.append(command)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "echo should-skip" not in executed

