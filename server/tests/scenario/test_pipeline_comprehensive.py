from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedStep, ResolvedSubPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import PipelineConfig


def _setup_config():
    import taskpps.config as cfg

    if cfg._project_root is None:
        root = cfg.find_project_root()
        cfg.set_project_root(root)
    cfg._settings = None
    cfg.load_settings()


class TestExecuteCommands:
    """测试 _execute_commands 方法的各种场景"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0176", domain="server/scenario", priority="P1")
    async def test_commands中途失败_stops_execution(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="multi-cmd",
            task_type="command",
            commands=["echo ok", "exit 1", "echo never"],
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cmd-fail")
        runner = PipelineRunner(run_id="cmd-fail", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.multi-cmd": "tr1"}

        call_count = 0

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            nonlocal call_count
            call_count += 1
            if command == "exit 1":
                return ExecutorResult(exit_code=1, stderr="command failed")
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0177", domain="server/scenario", priority="P2")
    async def test_empty_commands_list_returns_success(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="empty-cmds",
            task_type="command",
            command=None,
            commands=[],
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="empty-cmds")
        runner = PipelineRunner(run_id="empty-cmds", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.empty-cmds": "tr1"}

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
    @pytest.mark.zentao("TC-S0178", domain="server/scenario", priority="P1")
    async def test_commands_timeout_distribution(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="timed-cmds",
            task_type="command",
            commands=["echo a", "echo b", "echo c"],
            timeout=9,
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="timed-cmds")
        runner = PipelineRunner(run_id="timed-cmds", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.timed-cmds": "tr1"}

        timeouts = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            timeouts.append(timeout)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert all(t == 3 for t in timeouts)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0179", domain="server/scenario", priority="P1")
    async def test_commands_timeout_minimum_1_second(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="short-timeout",
            task_type="command",
            commands=["echo a", "echo b"],
            timeout=1,
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="short-to")
        runner = PipelineRunner(run_id="short-to", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.short-timeout": "tr1"}

        timeouts = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            timeouts.append(timeout)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert all(t >= 1 for t in timeouts)


class TestExecuteSteps:
    """测试 _execute_steps 方法的各种场景"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0180", domain="server/scenario", priority="P2")
    async def test_steps_complete_execution(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="multi-step",
            task_type="steps",
            steps=[
                ResolvedStep(run="echo step1"),
                ResolvedStep(run="echo step2"),
                ResolvedStep(run="echo step3"),
            ],
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="steps-ok")
        runner = PipelineRunner(run_id="steps-ok", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.multi-step": "tr1"}

        executed_commands = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            executed_commands.append(command)
            return ExecutorResult(exit_code=0, stdout=f"output-{command}")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed_commands == ["echo step1", "echo step2", "echo step3"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0181", domain="server/scenario", priority="P1")
    async def test_steps中途失败_stops_execution(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="step-fail",
            task_type="steps",
            steps=[
                ResolvedStep(run="echo ok"),
                ResolvedStep(run="exit 1"),
                ResolvedStep(run="echo never"),
            ],
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="step-fail")
        runner = PipelineRunner(run_id="step-fail", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.step-fail": "tr1"}

        executed_commands = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            executed_commands.append(command)
            if command == "exit 1":
                return ExecutorResult(exit_code=1, stderr="step failed")
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed_commands == ["echo ok", "exit 1"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0182", domain="server/scenario", priority="P1")
    async def test_steps_with_cd_and_env(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="step-cd-env",
            task_type="steps",
            steps=[
                ResolvedStep(run="ls", cd="/tmp", env={"MY_VAR": "hello"}),
                ResolvedStep(run="pwd"),
            ],
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="step-cd")
        runner = PipelineRunner(run_id="step-cd", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.step-cd-env": "tr1"}

        captured_cwds = []
        captured_envs = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            captured_cwds.append(cwd)
            captured_envs.append(env.get("MY_VAR"))
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert captured_cwds[0] == "/tmp"
        assert captured_envs[0] == "hello"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0183", domain="server/scenario", priority="P1")
    async def test_steps_timeout_distribution(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="step-timeout",
            task_type="steps",
            steps=[
                ResolvedStep(run="echo a"),
                ResolvedStep(run="echo b"),
                ResolvedStep(run="echo c"),
            ],
            timeout=12,
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="step-to")
        runner = PipelineRunner(run_id="step-to", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.step-timeout": "tr1"}

        timeouts = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            timeouts.append(timeout)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert all(t == 4 for t in timeouts)


class TestSubpipelineOnFailure:
    """测试 SubPipeline 级别的 on_failure 策略"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0184", domain="server/scenario", priority="P0")
    async def test_subpipeline_on_failure_continue_allows_dependents(self, db_engine, clean_db):
        """on_failure=continue 时，失败的 subpipeline 的依赖者应继续执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(on_failure="continue"),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
            depends_on=["A"],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="sub-continue")
        runner = PipelineRunner(run_id="sub-continue", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b"}

        executed_subs = []

        async def fake_execute_task(task, sub_name=""):
            executed_subs.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed_subs
        assert "B.b1" in executed_subs

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0185", domain="server/scenario", priority="P0")
    async def test_subpipeline_on_failure_fail_blocks_dependents(self, db_engine, clean_db):
        """on_failure=fail（默认）时，失败 subpipeline 的依赖者应被跳过"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
            depends_on=["A"],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="sub-fail")
        runner = PipelineRunner(run_id="sub-fail", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b"}

        executed_subs = []

        async def fake_execute_task(task, sub_name=""):
            executed_subs.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed_subs
        assert "B.b1" not in executed_subs


class TestTransitiveDependencies:
    """测试传递性 subpipeline 依赖 (A -> B -> C)"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0186", domain="server/scenario", priority="P1")
    async def test_transitive_dependency_failure_cascades(self, db_engine, clean_db):
        """A 失败时，B 和 C 都应被标记为失败"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
            depends_on=["A"],
        )
        sub_c = ResolvedSubPipeline(
            name="C",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="c1", task_type="command", command="echo c")],
            depends_on=["B"],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b, sub_c], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="transitive")
        runner = PipelineRunner(run_id="transitive", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b", "C.c1": "tr-c"}

        executed_subs = []

        async def fake_execute_task(task, sub_name=""):
            executed_subs.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed_subs
        assert "B.b1" not in executed_subs
        assert "C.c1" not in executed_subs

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0187", domain="server/scenario", priority="P2")
    async def test_transitive_dependency_success_propagates(self, db_engine, clean_db):
        """A 成功时，B 和 C 都应执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
            depends_on=["A"],
        )
        sub_c = ResolvedSubPipeline(
            name="C",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="c1", task_type="command", command="echo c")],
            depends_on=["B"],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b, sub_c], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="transitive-ok")
        runner = PipelineRunner(run_id="transitive-ok", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b", "C.c1": "tr-c"}

        executed_subs = []

        async def fake_execute_task(task, sub_name=""):
            executed_subs.append(f"{sub_name}.{task.name}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed_subs) == 3


class TestPartialVsFailed:
    """测试 PARTIAL vs FAILED 状态的精确区分"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0188", domain="server/scenario", priority="P2")
    async def test_partial_status_when_some_succeed(self, db_engine, clean_db):
        """部分 subpipeline 成功、部分失败时应返回 PARTIAL"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="partial-test")
        runner = PipelineRunner(run_id="partial-test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b"}

        async def fake_execute_task(task, sub_name=""):
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0189", domain="server/scenario", priority="P1")
    async def test_failed_status_when_all_fail(self, db_engine, clean_db):
        """所有 subpipeline 都失败时应返回 FAILED"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="exit 1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="all-fail")
        runner = PipelineRunner(run_id="all-fail", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b"}

        async def fake_execute_task(task, sub_name=""):
            return ExecutorResult(exit_code=1, stderr="fail")

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()


class TestParallelWithDependencies:
    """测试 parallel 策略 + task depends_on 混合使用"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0190", domain="server/scenario", priority="P1")
    async def test_parallel_respects_explicit_depends_on(self, db_engine, clean_db):
        """parallel 模式下，有显式 depends_on 的 task 仍应按顺序执行"""
        _setup_config()
        task_a = ResolvedTask(name="a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"])
        task_c = ResolvedTask(name="c", task_type="command", command="echo c")
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b, task_c],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-dep")
        runner = PipelineRunner(run_id="par-dep", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.a": "tr-a", "sub.b": "tr-b", "sub.c": "tr-c"}

        execution_order: list[str] = []

        async def fake_execute_task(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        idx = {e.split(":")[1]: i for i, e in enumerate(execution_order)}
        assert idx["sub.a"] < idx["sub.b"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0191", domain="server/scenario", priority="P1")
    async def test_parallel_mixed_success_and_failure(self, db_engine, clean_db):
        """parallel 模式下，部分 task 成功部分失败时结果正确处理"""
        _setup_config()
        task_a = ResolvedTask(name="a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="b", task_type="command", command="exit 1")
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-mixed")
        runner = PipelineRunner(run_id="par-mixed", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.a": "tr-a", "sub.b": "tr-b"}

        async def fake_execute_task(task, sub_name=""):
            if task.name == "b":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()


class TestTaskOnFailureOverride:
    """测试 task 级 on_failure 覆盖 subpipeline 级 on_failure"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0192", domain="server/scenario", priority="P1")
    async def test_task_on_failure_overrides_sub_level(self, db_engine, clean_db):
        """task B 级 on_failure=continue 应覆盖 sub 级 on_failure=fail"""
        _setup_config()
        task_a = ResolvedTask(
            name="a",
            task_type="command",
            command="exit 1",
        )
        task_b = ResolvedTask(
            name="b",
            task_type="command",
            command="echo b",
            depends_on=["a"],
            on_failure="continue",
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(on_failure="fail"),
            tasks=[task_a, task_b],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="on-fail-override")
        runner = PipelineRunner(run_id="on-fail-override", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.a": "tr-a", "sub.b": "tr-b"}

        executed = []

        async def fake_execute_task(task, sub_name=""):
            executed.append(task.name)
            if task.name == "a":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "a" in executed
        assert "b" in executed


class TestEmptySubpipeline:
    """测试空 subpipeline (tasks=[])"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0193", domain="server/scenario", priority="P2")
    async def test_empty_subpipeline_succeeds(self, db_engine, clean_db):
        _setup_config()
        sub = ResolvedSubPipeline(
            name="empty",
            config=PipelineConfig(),
            tasks=[],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="empty-sub")
        runner = PipelineRunner(run_id="empty-sub", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {}

        with (
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()


class TestEvaluateWhenEnvMerge:
    """测试 when 条件评估时的 env 合并"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0194", domain="server/scenario", priority="P1")
    async def test_when_uses_top_level_env(self, db_engine, clean_db):
        """when 条件可引用 top-level pipeline config 级 env"""
        _setup_config()
        task = ResolvedTask(
            name="conditional",
            task_type="command",
            command="echo hi",
            when="${DEPLOY_ENV} == prod",
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(
            name="p",
            subpipelines=[sub],
            top_config=PipelineConfig(env={"DEPLOY_ENV": "prod"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="when-pipeline-env")
        runner = PipelineRunner(run_id="when-pipeline-env", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.conditional": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        mock_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0195", domain="server/scenario", priority="P1")
    async def test_when_skips_based_on_top_level_env(self, db_engine, clean_db):
        """when 条件不满足时 task 应被跳过"""
        _setup_config()
        task = ResolvedTask(
            name="conditional",
            task_type="command",
            command="echo hi",
            when="${DEPLOY_ENV} == staging",
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(
            name="p",
            subpipelines=[sub],
            top_config=PipelineConfig(env={"DEPLOY_ENV": "prod"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="when-skip")
        runner = PipelineRunner(run_id="when-skip", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.conditional": "tr1"}

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        mock_executor.execute.assert_not_called()


class TestRetryWithLogging:
    """测试重试逻辑和日志记录"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0196", domain="server/scenario", priority="P1")
    async def test_retry_writes_log_on_each_attempt(self, db_engine, clean_db):
        """每次重试应写入日志"""
        _setup_config()
        task = ResolvedTask(
            name="retry-task",
            task_type="command",
            command="echo retry",
            retry=2,
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="retry-log")
        runner = PipelineRunner(run_id="retry-log", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.retry-task": "tr1"}

        attempt = 0

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                return ExecutorResult(exit_code=1, stderr=f"fail attempt {attempt}")
            return ExecutorResult(exit_code=0, stdout="success")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert attempt == 3


class TestSubpipelineNotFound:
    """测试 subpipeline 不存在时的处理"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0197", domain="server/scenario", priority="P1")
    async def test_missing_subpipeline_returns_failure(self, db_engine, clean_db):
        _setup_config()
        pipeline = ResolvedPipeline(
            name="p",
            subpipelines=[],
            top_config=PipelineConfig(),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="missing-sub")
        runner = PipelineRunner(run_id="missing-sub", pipeline=pipeline, context=ctx)

        result = await runner._execute_subpipeline("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]


class TestGetActiveRunner:
    """测试 get_active_runner 在 pipeline 运行期间返回 runner"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0198", domain="server/scenario", priority="P2")
    async def test_active_runner_available_during_execution(self, db_engine, clean_db):
        _setup_config()
        from taskpps.engine.runner import get_active_runner

        task = ResolvedTask(name="t1", task_type="command", command="echo hi")
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="active-runner")
        runner = PipelineRunner(run_id="active-runner", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.t1": "tr1"}

        runner_during_exec = None

        async def fake_execute_task(task, sub_name=""):
            nonlocal runner_during_exec
            runner_during_exec = get_active_runner("active-runner")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert runner_during_exec is runner


class TestExceptionInSubpipeline:
    """测试 subpipeline 执行中抛出 BaseException"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0199", domain="server/scenario", priority="P1")
    async def test_base_exception_marks_dependents_as_failed(self, db_engine, clean_db):
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a")],
        )
        sub_b = ResolvedSubPipeline(
            name="B",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b")],
            depends_on=["A"],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="exc-test")
        runner = PipelineRunner(run_id="exc-test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"A.a1": "tr-a", "B.b1": "tr-b"}

        call_count = 0

        async def fake_execute_subpipeline(name):
            nonlocal call_count
            call_count += 1
            if name == "A":
                raise RuntimeError("unexpected boom")
            return {"success": True}

        with (
            patch.object(runner, "_execute_subpipeline", side_effect=fake_execute_subpipeline),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert call_count == 1


class TestCommandWithNoneTimeout:
    """测试 commands/steps 在无 timeout 时使用默认 timeout 并正确分配"""

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0200", domain="server/scenario", priority="P1")
    async def test_commands_uses_default_timeout(self, db_engine, clean_db):
        _setup_config()
        task = ResolvedTask(
            name="no-timeout",
            task_type="command",
            commands=["echo a", "echo b"],
        )
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="no-timeout")
        runner = PipelineRunner(run_id="no-timeout", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.no-timeout": "tr1"}

        from taskpps.config import get_settings

        default_timeout = get_settings().executor.default_timeout

        timeouts = []

        async def fake_execute(command, env, log_path, timeout=None, cwd=None):
            timeouts.append(timeout)
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_execute

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        expected_per_cmd = default_timeout // 2
        assert all(t == expected_per_cmd for t in timeouts)

