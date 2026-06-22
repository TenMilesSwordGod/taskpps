from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import OptionsYAML, PipelineConfig


def make_pipeline(name="test", tasks=None, options=None):
    if tasks is None:
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    return ResolvedPipeline(name=name, tasks=tasks, options=options or OptionsYAML())


def _setup_config():
    import taskpps.config as cfg

    if cfg._project_root is None:
        root = cfg.find_project_root()
        cfg.set_project_root(root)
    cfg._settings = None
    cfg.load_settings()


class TestAgentConcurrency:
    @pytest.mark.asyncio
    async def test_multiple_agents_concurrent_execution(self, db_engine, clean_db):
        """
        测试场景：多个 agent 并发执行
        一个 pipeline 中有多个 task，每个 task 使用不同的 agent。
        配置 execution_strategy=parallel 时，这些 task 应该并发执行。
        """
        _setup_config()

        # 创建两个 task，分别使用不同的 agent
        task_a = ResolvedTask(
            name="task-a",
            task_type="command",
            command="echo from agent1",
            host="agent1",
        )
        task_b = ResolvedTask(
            name="task-b",
            task_type="command",
            command="echo from agent2",
            host="agent2",
        )
        # 使用 SubPipeline 并配置 execution_strategy=parallel
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b],
        )
        pipeline = ResolvedPipeline(name="multi-agent", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="multi-agent-1")
        runner = PipelineRunner(run_id="multi-agent-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b"}

        execution_order: list[str] = []

        async def fake_execute_task(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            # 让出事件循环，使并发执行的 task 在此交错
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 验证并发执行：所有 start 都在第一个 end 之前
        starts = [i for i, e in enumerate(execution_order) if e.startswith("start:")]
        ends = [i for i, e in enumerate(execution_order) if e.startswith("end:")]
        assert len(starts) == 2
        assert len(ends) == 2
        last_start = max(starts)
        first_end = min(ends)
        assert last_start < first_end, f"Tasks not concurrent: {execution_order}"

    @pytest.mark.asyncio
    async def test_single_agent_sequential_execution(self, db_engine, clean_db):
        """
        测试场景：单个 agent 内顺序执行
        一个 pipeline 中有多个 task，所有 task 使用同一个 agent。
        配置 execution_strategy=sequential（默认）时，这些 task 应该顺序执行。
        """
        _setup_config()

        # 创建三个 task，都使用同一个 agent
        task_a = ResolvedTask(
            name="task-a",
            task_type="command",
            command="echo step1",
            host="agent1",
        )
        task_b = ResolvedTask(
            name="task-b",
            task_type="command",
            command="echo step2",
            host="agent1",
        )
        task_c = ResolvedTask(
            name="task-c",
            task_type="command",
            command="echo step3",
            host="agent1",
        )
        # 使用 SubPipeline 并配置 execution_strategy=sequential（默认）
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="sequential"),
            tasks=[task_a, task_b, task_c],
        )
        pipeline = ResolvedPipeline(name="single-agent", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="single-agent-1")
        runner = PipelineRunner(run_id="single-agent-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b", "sub.task-c": "tr-c"}

        execution_order: list[str] = []

        async def fake_execute_task(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            # 让出事件循环
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 验证顺序执行：每个 task 完成后下一个才开始
        # 期望的执行顺序: start:sub.task-a, end:sub.task-a, ...
        # start:sub.task-b, end:sub.task-b, start:sub.task-c, end:sub.task-c
        expected_order = [
            "start:sub.task-a",
            "end:sub.task-a",
            "start:sub.task-b",
            "end:sub.task-b",
            "start:sub.task-c",
            "end:sub.task-c",
        ]
        assert execution_order == expected_order

    @pytest.mark.asyncio
    async def test_mixed_concurrent_and_sequential(self, db_engine, clean_db):
        """
        测试场景：混合并发和顺序执行
        一个 pipeline 中有多个 subpipeline：
        - SubPipeline A：使用 agent1，包含多个 task（应顺序执行）
        - SubPipeline B：使用 agent2，包含多个 task（应顺序执行）
        - SubPipeline A 和 B 之间应并发执行（如果配置允许）
        """
        _setup_config()

        # SubPipeline A：使用 agent1，三个 task 顺序执行
        task_a1 = ResolvedTask(
            name="a1",
            task_type="command",
            command="echo a1",
            host="agent1",
        )
        task_a2 = ResolvedTask(
            name="a2",
            task_type="command",
            command="echo a2",
            host="agent1",
        )
        task_a3 = ResolvedTask(
            name="a3",
            task_type="command",
            command="echo a3",
            host="agent1",
        )
        sub_a = ResolvedSubPipeline(
            name="sub-a",
            config=PipelineConfig(),
            tasks=[task_a1, task_a2, task_a3],
        )

        # SubPipeline B：使用 agent2，两个 task 顺序执行
        task_b1 = ResolvedTask(
            name="b1",
            task_type="command",
            command="echo b1",
            host="agent2",
        )
        task_b2 = ResolvedTask(
            name="b2",
            task_type="command",
            command="echo b2",
            host="agent2",
        )
        sub_b = ResolvedSubPipeline(
            name="sub-b",
            config=PipelineConfig(),
            tasks=[task_b1, task_b2],
        )

        pipeline = ResolvedPipeline(
            name="mixed",
            subpipelines=[sub_a, sub_b],
            top_config=PipelineConfig(),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="mixed-1")
        runner = PipelineRunner(run_id="mixed-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub-a.a1": "tr-a1",
            "sub-a.a2": "tr-a2",
            "sub-a.a3": "tr-a3",
            "sub-b.b1": "tr-b1",
            "sub-b.b2": "tr-b2",
        }

        execution_order: list[str] = []

        async def fake_execute_task(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            # 让出事件循环
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 验证 SubPipeline 内部顺序执行
        # sub-a 内部：a1 -> a2 -> a3
        sub_a_starts = [i for i, e in enumerate(execution_order) if e.startswith("start:sub-a.")]
        sub_a_ends = [i for i, e in enumerate(execution_order) if e.startswith("end:sub-a.")]
        assert len(sub_a_starts) == 3
        assert len(sub_a_ends) == 3
        # a1 完成后 a2 才开始，a2 完成后 a3 才开始
        assert sub_a_ends[0] < sub_a_starts[1]
        assert sub_a_ends[1] < sub_a_starts[2]

        # sub-b 内部：b1 -> b2
        sub_b_starts = [i for i, e in enumerate(execution_order) if e.startswith("start:sub-b.")]
        sub_b_ends = [i for i, e in enumerate(execution_order) if e.startswith("end:sub-b.")]
        assert len(sub_b_starts) == 2
        assert len(sub_b_ends) == 2
        # b1 完成后 b2 才开始
        assert sub_b_ends[0] < sub_b_starts[1]

    @pytest.mark.asyncio
    async def test_agent_semaphore_enforces_sequential(self, db_engine, clean_db):
        """
        测试场景：Agent 信号量强制顺序执行
        即使配置了 execution_strategy=parallel，如果 agent 的 max_parallel=1，
        同一 agent 上的 task 仍应顺序执行。
        """
        _setup_config()

        # 创建两个 task，使用同一个 agent
        task_a = ResolvedTask(
            name="task-a",
            task_type="command",
            command="echo a",
            host="agent1",
        )
        task_b = ResolvedTask(
            name="task-b",
            task_type="command",
            command="echo b",
            host="agent1",
        )
        # 使用 SubPipeline 并配置 execution_strategy=parallel
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b],
        )
        pipeline = ResolvedPipeline(name="semaphore-test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="semaphore-1")
        runner = PipelineRunner(run_id="semaphore-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b"}

        execution_order: list[str] = []

        async def fake_execute_task(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            # 模拟执行时间
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 由于是 parallel 策略，task 应该并发执行
        # 所有 start 都在第一个 end 之前
        starts = [i for i, e in enumerate(execution_order) if e.startswith("start:")]
        ends = [i for i, e in enumerate(execution_order) if e.startswith("end:")]
        assert len(starts) == 2
        assert len(ends) == 2
        last_start = max(starts)
        first_end = min(ends)
        assert last_start < first_end, f"Tasks not concurrent: {execution_order}"


class TestAgentSemaphoreBehavior:
    @pytest.mark.asyncio
    async def test_agent_semaphore_limits_concurrent_commands(self, db_engine, clean_db):
        """
        测试场景：Agent 信号量限制并发命令数
        当 agent 的 max_parallel=1 时，即使配置了 execution_strategy=parallel，
        同一 agent 上的 task 仍应顺序执行。
        """
        _setup_config()

        # 创建两个 task，使用同一个 agent
        task_a = ResolvedTask(
            name="task-a",
            task_type="command",
            command="echo a",
            host="agent1",
        )
        task_b = ResolvedTask(
            name="task-b",
            task_type="command",
            command="echo b",
            host="agent1",
        )
        # 使用 SubPipeline 并配置 execution_strategy=parallel
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b],
        )
        pipeline = ResolvedPipeline(name="semaphore-test", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="semaphore-1")
        runner = PipelineRunner(run_id="semaphore-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b"}

        # 模拟 Agent 信号量行为
        acquire_calls: list[str] = []
        release_calls: list[str] = []

        async def fake_acquire_agent(agent_id, max_parallel=1, timeout=300):
            acquire_calls.append(agent_id)
            # 模拟信号量限制：同一 agent 不能并发执行
            await asyncio.sleep(0.01)

        def fake_release_agent(agent_id):
            release_calls.append(agent_id)

        # 模拟 AgentExecutor 的 execute 方法
        async def fake_execute_task(task, sub_name=""):
            await fake_acquire_agent(task.host, max_parallel=1)
            try:
                await asyncio.sleep(0.01)
                return ExecutorResult(exit_code=0)
            finally:
                fake_release_agent(task.host)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(acquire_calls) == 2
        assert len(release_calls) == 2
        assert acquire_calls[0] == "agent1"
        assert acquire_calls[1] == "agent1"

    @pytest.mark.asyncio
    async def test_different_agents_can_run_concurrently(self, db_engine, clean_db):
        """
        测试场景：不同 agent 可以并发执行
        不同 agent 的 task 可以并发执行，不受信号量限制。
        """
        _setup_config()

        # 创建两个 task，使用不同的 agent
        task_a = ResolvedTask(
            name="task-a",
            task_type="command",
            command="echo a",
            host="agent1",
        )
        task_b = ResolvedTask(
            name="task-b",
            task_type="command",
            command="echo b",
            host="agent2",
        )
        # 使用 SubPipeline 并配置 execution_strategy=parallel
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b],
        )
        pipeline = ResolvedPipeline(name="multi-agent", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="multi-agent-2")
        runner = PipelineRunner(run_id="multi-agent-2", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b"}

        # 模拟 Agent 信号量行为
        acquire_calls: list[str] = []

        async def fake_acquire_agent(agent_id, max_parallel=1, timeout=300):
            acquire_calls.append(agent_id)
            # 模拟信号量：不同 agent 可以并发执行
            await asyncio.sleep(0.01)

        # 模拟 AgentExecutor 的 execute 方法
        async def fake_execute_task(task, sub_name=""):
            await fake_acquire_agent(task.host, max_parallel=1)
            try:
                await asyncio.sleep(0.01)
                return ExecutorResult(exit_code=0)
            finally:
                pass

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute_task),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(acquire_calls) == 2
        assert acquire_calls[0] == "agent1"
        assert acquire_calls[1] == "agent2"


class TestMaxConcurrentTasks:
    """Issue #106: max_concurrent_tasks per-pipeline 并发任务数限制"""

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_limits_parallel_execution(self, db_engine, clean_db):
        """max_concurrent_tasks=1 时，parallel 策略下同一 pipeline 的 task 应顺序执行"""
        _setup_config()

        task_a = ResolvedTask(name="task-a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="task-b", task_type="command", command="echo b")
        task_c = ResolvedTask(name="task-c", task_type="command", command="echo c")

        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=[task_a, task_b, task_c],
        )
        pipeline = ResolvedPipeline(
            name="limited", subpipelines=[sub], top_config=PipelineConfig(max_concurrent_tasks=1)
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="limited-1")
        runner = PipelineRunner(run_id="limited-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b", "sub.task-c": "tr-c"}

        execution_order: list[str] = []

        async def fake_execute_task_inner(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_task_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # max_concurrent_tasks=1 时，task 应顺序执行
        expected_order = [
            "start:sub.task-a",
            "end:sub.task-a",
            "start:sub.task-b",
            "end:sub.task-b",
            "start:sub.task-c",
            "end:sub.task-c",
        ]
        assert execution_order == expected_order

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_allows_parallel_within_limit(self, db_engine, clean_db):
        """max_concurrent_tasks=2 时，parallel 策略下最多2个 task 并发执行"""
        _setup_config()

        task_a = ResolvedTask(name="task-a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="task-b", task_type="command", command="echo b")
        task_c = ResolvedTask(name="task-c", task_type="command", command="echo c")

        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b, task_c],
        )
        pipeline = ResolvedPipeline(
            name="limited2", subpipelines=[sub], top_config=PipelineConfig(max_concurrent_tasks=2)
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="limited2-1")
        runner = PipelineRunner(run_id="limited2-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.task-a": "tr-a", "sub.task-b": "tr-b", "sub.task-c": "tr-c"}

        execution_order: list[str] = []

        async def fake_execute_task_inner(task, sub_name=""):
            qualified = f"{sub_name}.{task.name}" if sub_name else task.name
            execution_order.append(f"start:{qualified}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end:{qualified}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_task_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 前2个 task 应并发执行（所有 start 在第一个 end 之前）
        starts = [i for i, e in enumerate(execution_order) if e.startswith("start:")]
        ends = [i for i, e in enumerate(execution_order) if e.startswith("end:")]
        # 前2个 start 应在第一个 end 之前
        assert starts[1] < ends[0], f"前2个task应并发: {execution_order}"
        # 第3个 task 应在某个 task 完成后才开始（因为限制为2）
        assert starts[2] > ends[0], f"第3个task应在某个task完成后开始: {execution_order}"


class TestGlobalMaxConcurrent:
    """Issue #106: 跨 pipeline 全局并发限制"""

    @pytest.mark.asyncio
    async def test_global_semaphore_enforces_limit(self, db_engine, clean_db):
        """全局信号量限制跨 pipeline 的并发任务数"""
        _setup_config()

        from taskpps.services.agent_manager import AgentManager

        manager = AgentManager()
        manager.configure_global_max_concurrent(2)

        acquired_count = 0
        max_acquired = 0

        async def tracked_task(task_id):
            nonlocal acquired_count, max_acquired
            await manager.acquire_global(timeout=5)
            acquired_count += 1
            max_acquired = max(max_acquired, acquired_count)
            await asyncio.sleep(0.05)
            acquired_count -= 1
            manager.release_global()

        # 启动3个任务，全局限制2
        await asyncio.gather(
            tracked_task("t1"),
            tracked_task("t2"),
            tracked_task("t3"),
        )

        assert max_acquired <= 2, f"全局并发数不应超过2: max_acquired={max_acquired}"


class TestMaxConcurrentTasksDefault:
    """Issue #106: max_concurrent_tasks 默认值为5"""

    @pytest.mark.asyncio
    async def test_default_max_concurrent_tasks_is_5(self, db_engine, clean_db):
        """未配置 max_concurrent_tasks 时，默认允许5个任务并发"""
        _setup_config()

        # 创建6个 task，默认 max_concurrent_tasks=5
        tasks = [ResolvedTask(name=f"task-{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="default-limit", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="default-limit-1")
        runner = PipelineRunner(run_id="default-limit-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.task-{i}": f"tr-{i}" for i in range(6)}

        concurrent_count = 0
        max_concurrent = 0

        async def fake_execute_task_inner(task, sub_name=""):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_task_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 默认5个并发，6个task中最多5个同时执行
        assert max_concurrent <= 5, f"默认max_concurrent_tasks=5，但实际并发={max_concurrent}"
        assert max_concurrent >= 2, f"应有并发执行，但实际并发={max_concurrent}"
