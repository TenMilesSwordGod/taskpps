"""针对 issue #123 修复的独立测试。

补充现有 test_parallel_sequential_edge_cases.py 的覆盖缺口:

1. 现有测试中 top_config 均为默认值,导致 _task_semaphore 默认为 5,与
   sub.config.max_concurrent_tasks 的限制值相同,无法区分两层信号量中
   哪一层在生效。本文件用 top_config.max_concurrent_tasks 严格小于
   sub.config.max_concurrent_tasks 的设置验证 _task_semaphore 真的被 acquire。

2. 负数 max_concurrent_tasks 应当 fallback 到默认 5。
3. top_config 限制应跨 subpipeline 生效(同 level 内的 subpipeline 串行执行,
   但任务执行受 _task_semaphore 限制)。

注意:必须 mock _execute_task_inner 而非 _execute_task,否则 _task_semaphore
的 acquire/release 逻辑不会执行(它在 _execute_task 包装层)。
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask
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


class TestTopConfigSemaphoreEnforcement:
    """验证 _task_semaphore(pipeline 全局)真的在 _execute_task 中被 acquire。

    关键设置:sub.config.max_concurrent_tasks 比 top_config 大,
    这样如果 _task_semaphore 没生效,就会观察到更高并发。

    实现要点:必须 mock _execute_task_inner,这样 _execute_task 包装层的
    semaphore.acquire/release 仍会执行。
    """

    @pytest.mark.asyncio
    async def test_top_config_limit_1_overrides_sub_limit_5(self, db_engine, clean_db):
        """top_config=1 + sub.config=5 时,实际并发应被 _task_semaphore 限制为 1。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=5),
            tasks=tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=1)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="top1-sub5")
        runner = PipelineRunner(run_id="top1-sub5", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(4)}

        max_inflight = 0
        inflight = 0

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 1, (
            f"_task_semaphore 应将并发限制为 1,实际={max_inflight}。"
            f"若 max_inflight > 1,说明 _task_semaphore 未生效(issue #123 原始 bug)"
        )

    @pytest.mark.asyncio
    async def test_top_config_limit_2_with_sub_limit_5(self, db_engine, clean_db):
        """top_config=2 + sub.config=5 时,实际并发应被 _task_semaphore 限制为 2。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=5),
            tasks=tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=2)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="top2-sub5")
        runner = PipelineRunner(run_id="top2-sub5", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(6)}

        max_inflight = 0
        inflight = 0

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 2, (
            f"_task_semaphore 应将并发限制为 2,实际={max_inflight}。"
            f"若 max_inflight > 2,说明 _task_semaphore 未生效"
        )

    @pytest.mark.asyncio
    async def test_top_config_smaller_wins_over_sub(self, db_engine, clean_db):
        """top_config=1 + sub.config=2:实际并发=1(取 min)。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=1)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="min-test")
        runner = PipelineRunner(run_id="min-test", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(4)}

        max_inflight = 0
        inflight = 0

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 1, f"两层信号量 min(1,2)=1,实际={max_inflight}"


class TestTopConfigFallback:
    """验证 top_config.max_concurrent_tasks 的边界值 fallback 行为。

    代码逻辑:
        if not isinstance(max_concurrent_tasks, int) or max_concurrent_tasks <= 0:
            max_concurrent_tasks = 5
    """

    @pytest.mark.asyncio
    async def test_top_config_zero_falls_back_to_default(self, db_engine, clean_db):
        """top_config.max_concurrent_tasks=0 时,_task_semaphore 应使用默认 5。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=10),
            tasks=tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=0)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="top-zero")
        runner = PipelineRunner(run_id="top-zero", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(6)}

        max_inflight = 0
        inflight = 0

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # top_config=0 -> fallback 5,sub=10,实际并发=min(5,10)=5
        assert max_inflight == 5, f"top_config=0 应 fallback 到 5,实际={max_inflight}"

    @pytest.mark.asyncio
    async def test_top_config_negative_falls_back_to_default(self, db_engine, clean_db):
        """top_config.max_concurrent_tasks=-3 时,应 fallback 到默认 5。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=10),
            tasks=tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=-3)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="top-neg")
        runner = PipelineRunner(run_id="top-neg", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(6)}

        max_inflight = 0
        inflight = 0

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 5, f"top_config=-3 应 fallback 到 5,实际={max_inflight}"


class TestTopConfigAcrossSubpipelines:
    """验证 _task_semaphore 跨 subpipeline 限制(同 level 内 subpipeline 串行,但任务并发受限)。"""

    @pytest.mark.asyncio
    async def test_top_config_limit_across_sequential_subpipelines(self, db_engine, clean_db):
        """两个 sequential subpipeline 串行执行,但每 sub 内部并发受 _task_semaphore 限制。"""
        _setup_config()
        sub1_tasks = [ResolvedTask(name=f"s1t{i}", task_type="command", command=f"echo s1t{i}") for i in range(3)]
        sub1 = ResolvedSubPipeline(
            name="sub1",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=10),
            tasks=sub1_tasks,
        )
        sub2_tasks = [ResolvedTask(name=f"s2t{i}", task_type="command", command=f"echo s2t{i}") for i in range(3)]
        sub2 = ResolvedSubPipeline(
            name="sub2",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=10),
            depends_on=["sub1"],
            tasks=sub2_tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=2)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub1, sub2], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="top-cross")
        runner = PipelineRunner(run_id="top-cross", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "sub1.s1t0": "tr1-0",
            "sub1.s1t1": "tr1-1",
            "sub1.s1t2": "tr1-2",
            "sub2.s2t0": "tr2-0",
            "sub2.s2t1": "tr2-1",
            "sub2.s2t2": "tr2-2",
        }

        max_inflight = 0
        inflight = 0

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # top_config=2, sub=10,实际并发=min(2,10)=2
        assert max_inflight == 2, f"_task_semaphore 跨 subpipeline 限制应为 2,实际={max_inflight}"


class TestTaskSemaphoreInit:
    """验证 _task_semaphore 在 run() 时被正确创建(issue #123 原始 bug 的核心)。"""

    @pytest.mark.asyncio
    async def test_task_semaphore_created_in_run(self, db_engine, clean_db):
        """run() 调用后 _task_semaphore 应被创建且 limit 与 top_config 一致。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(2)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=3),
            tasks=tasks,
        )
        top_config = PipelineConfig(max_concurrent_tasks=2)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=top_config)
        ctx = ExecutionContext(pipeline=pipeline, run_id="sem-init")
        runner = PipelineRunner(run_id="sem-init", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(2)}

        async def fake_execute_inner(task, sub_name="", max_parallel=None):
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task_inner", side_effect=fake_execute_inner),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # _task_semaphore 必须在 run() 中被创建
        assert runner._task_semaphore is not None, "_task_semaphore 应在 run() 中被创建(issue #106/#123 原始修复)"
        # asyncio.Semaphore 没有公开的 _value 属性,但内部 _value 在 3.10+ 可访问
        assert runner._task_semaphore._value == 2, (
            f"_task_semaphore 应 limit=2(top_config.max_concurrent_tasks),"
            f"实际 _value={runner._task_semaphore._value}"
        )
