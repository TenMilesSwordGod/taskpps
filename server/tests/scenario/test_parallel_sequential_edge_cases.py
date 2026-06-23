from __future__ import annotations

import asyncio
import time
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


class TestMaxConcurrentTasksEnforcement:
    """测试 max_concurrent_tasks 信号量对 parallel 任务的实际并发限制。

    这些测试验证:当 max_concurrent_tasks=N 时,同一 level 内最多 N 个 task
    真正同时运行,其余 task 在队列中等待(不靠 mock sleep 时序推断,而是用
    并发计数器精确断言)。
    """

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_1_forces_serial(self, db_engine, clean_db):
        """max_concurrent_tasks=1 时,parallel 策略的 task 实际仍串行执行"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="mc1")
        runner = PipelineRunner(run_id="mc1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(4)}

        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 1, f"max_concurrent_tasks=1 下并发数不应超过1,实际={max_inflight}"

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_2_allows_two_parallel(self, db_engine, clean_db):
        """max_concurrent_tasks=2 时,4 个 task 最多 2 个并发"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="mc2")
        runner = PipelineRunner(run_id="mc2", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(4)}

        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 2, f"max_concurrent_tasks=2 下并发数应为2,实际={max_inflight}"

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_3_with_6_tasks(self, db_engine, clean_db):
        """max_concurrent_tasks=3 时,6 个 task 最多 3 个并发"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=3),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="mc3")
        runner = PipelineRunner(run_id="mc3", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(6)}

        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight == 3, f"max_concurrent_tasks=3 下并发数应为3,实际={max_inflight}"

    @pytest.mark.asyncio
    async def test_all_tasks_eventually_complete_with_queue(self, db_engine, clean_db):
        """max_concurrent_tasks=1 时,所有 task 最终都完成(队列不丢失任务)"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(5)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="queue-complete")
        runner = PipelineRunner(run_id="queue-complete", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(5)}

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(task.name)
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed_tasks) == 5, f"所有 task 应完成,实际执行了 {len(executed_tasks)} 个"
        assert set(executed_tasks) == {f"t{i}" for i in range(5)}


class TestTaskQueueWaitBehavior:
    """测试 task 在信号量队列中等待的边缘场景。

    关注点:当并行 task 数超过 max_concurrent_tasks 时,
    排队的 task 是否正确等待、完成后是否释放信号量给下一个。
    """

    @pytest.mark.asyncio
    async def test_queued_tasks_start_after_earlier_completes(self, db_engine, clean_db):
        """排队的 task 在前面的 task 完成后才启动"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(3)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="queue-wait")
        runner = PipelineRunner(run_id="queue-wait", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(3)}

        start_times: dict[str, float] = {}
        end_times: dict[str, float] = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            start_times[task.name] = time.monotonic()
            await asyncio.sleep(0.03)
            end_times[task.name] = time.monotonic()
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 串行执行时,t0 结束后 t1 才开始,t1 结束后 t2 才开始
        assert end_times["t0"] <= start_times["t1"], "t0 结束后 t1 才应开始"
        assert end_times["t1"] <= start_times["t2"], "t1 结束后 t2 才应开始"

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_failure(self, db_engine, clean_db):
        """task 失败后信号量应释放,后续排队 task 不被永久阻塞"""
        _setup_config()
        tasks = [
            ResolvedTask(name="t0", task_type="command", command="exit 1"),
            ResolvedTask(name="t1", task_type="command", command="echo 1"),
            ResolvedTask(name="t2", task_type="command", command="echo 2"),
        ]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(
                execution_strategy="parallel",
                max_concurrent_tasks=1,
                on_failure="continue",
            ),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="sem-release")
        runner = PipelineRunner(run_id="sem-release", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(3)}

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(task.name)
            if task.name == "t0":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "t1" in executed_tasks, "t0 失败后 t1 不应被永久阻塞"
        assert "t2" in executed_tasks, "t0 失败后 t2 不应被永久阻塞"

    @pytest.mark.asyncio
    async def test_all_tasks_complete_same_timestamp_in_unlimited_parallel(self, db_engine, clean_db):
        """无 max_concurrent_tasks 限制时,所有 task 应同时启动"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(5)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="unlimited")
        runner = PipelineRunner(run_id="unlimited", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(5)}

        start_times: dict[str, float] = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            start_times[task.name] = time.monotonic()
            await asyncio.sleep(0.02)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        times = list(start_times.values())
        # 所有 task 启动时间差应非常小(< 5ms),说明是并发的
        spread = max(times) - min(times)
        assert spread < 0.005, f"无限制时 task 应同时启动,时间差={spread:.4f}s"


class TestMixedParallelSequentialSubpipelines:
    """测试 parallel 和 sequential 策略的 subpipeline 混合使用场景。

    这些测试覆盖多个 subpipeline 之间有不同的 execution_strategy,
    并验证跨策略的依赖传播和执行顺序。
    """

    @pytest.mark.asyncio
    async def test_parallel_sub_then_sequential_sub(self, db_engine, clean_db):
        """parallel subpipeline 完成后 sequential subpipeline 开始执行"""
        _setup_config()
        # Sub 1: parallel
        p_task_a = ResolvedTask(name="a", task_type="command", command="echo pa")
        p_task_b = ResolvedTask(name="b", task_type="command", command="echo pb")
        sub_parallel = ResolvedSubPipeline(
            name="parallel-sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[p_task_a, p_task_b],
        )
        # Sub 2: sequential, depends on sub 1
        s_task_x = ResolvedTask(name="x", task_type="command", command="echo sx")
        s_task_y = ResolvedTask(name="y", task_type="command", command="echo sy", depends_on=["x"])
        sub_sequential = ResolvedSubPipeline(
            name="sequential-sub",
            config=PipelineConfig(execution_strategy="sequential"),
            depends_on=["parallel-sub"],
            tasks=[s_task_x, s_task_y],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_parallel, sub_sequential], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-seq-mix")
        runner = PipelineRunner(run_id="par-seq-mix", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "parallel-sub.a": "tr-a",
            "parallel-sub.b": "tr-b",
            "sequential-sub.x": "tr-x",
            "sequential-sub.y": "tr-y",
        }

        sub_start_order: list[str] = []
        current_sub = ""

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal current_sub
            if sub_name and current_sub != sub_name:
                sub_start_order.append(sub_name)
                current_sub = sub_name
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert sub_start_order.index("parallel-sub") < sub_start_order.index("sequential-sub"), (
            "parallel-sub 应先于 sequential-sub 执行"
        )

    @pytest.mark.asyncio
    async def test_sequential_sub_then_parallel_sub(self, db_engine, clean_db):
        """sequential subpipeline 完成后 parallel subpipeline 开始执行"""
        _setup_config()
        s_task_a = ResolvedTask(name="a", task_type="command", command="echo sa")
        sub_sequential = ResolvedSubPipeline(
            name="seq-sub",
            config=PipelineConfig(execution_strategy="sequential"),
            tasks=[s_task_a],
        )
        p_task_x = ResolvedTask(name="x", task_type="command", command="echo px")
        p_task_y = ResolvedTask(name="y", task_type="command", command="echo py")
        sub_parallel = ResolvedSubPipeline(
            name="par-sub",
            config=PipelineConfig(execution_strategy="parallel"),
            depends_on=["seq-sub"],
            tasks=[p_task_x, p_task_y],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_sequential, sub_parallel], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="seq-par-mix")
        runner = PipelineRunner(run_id="seq-par-mix", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "seq-sub.a": "tr-a",
            "par-sub.x": "tr-x",
            "par-sub.y": "tr-y",
        }

        sub_start_order: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            if sub_name and (not sub_start_order or sub_start_order[-1] != sub_name):
                sub_start_order.append(sub_name)
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert sub_start_order.index("seq-sub") < sub_start_order.index("par-sub"), "seq-sub 应先于 par-sub 执行"

    @pytest.mark.asyncio
    async def test_parallel_sub_failure_skips_dependent_sequential_sub(self, db_engine, clean_db):
        """parallel subpipeline 失败后,依赖它的 sequential subpipeline 应被跳过"""
        _setup_config()
        p_task = ResolvedTask(name="fail", task_type="command", command="exit 1")
        sub_parallel = ResolvedSubPipeline(
            name="par-fail",
            config=PipelineConfig(execution_strategy="parallel", on_failure="fail"),
            tasks=[p_task],
        )
        s_task = ResolvedTask(name="s", task_type="command", command="echo s")
        sub_sequential = ResolvedSubPipeline(
            name="seq-dep",
            config=PipelineConfig(execution_strategy="sequential"),
            depends_on=["par-fail"],
            tasks=[s_task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_parallel, sub_sequential], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-fail-skip")
        runner = PipelineRunner(run_id="par-fail-skip", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "par-fail.fail": "tr-fail",
            "seq-dep.s": "tr-s",
        }

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(f"{sub_name}.{task.name}")
            if task.name == "fail":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "seq-dep.s" not in executed_tasks, "par-fail 失败后 seq-dep.s 不应执行"

    @pytest.mark.asyncio
    async def test_parallel_sub_failure_continue_runs_dependent(self, db_engine, clean_db):
        """parallel subpipeline on_failure=continue 时,依赖它的 subpipeline 仍应执行"""
        _setup_config()
        p_task = ResolvedTask(name="fail", task_type="command", command="exit 1")
        sub_parallel = ResolvedSubPipeline(
            name="par-continue",
            config=PipelineConfig(execution_strategy="parallel", on_failure="continue"),
            tasks=[p_task],
        )
        s_task = ResolvedTask(name="s", task_type="command", command="echo s")
        sub_sequential = ResolvedSubPipeline(
            name="seq-after",
            config=PipelineConfig(execution_strategy="sequential"),
            depends_on=["par-continue"],
            tasks=[s_task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_parallel, sub_sequential], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-cont-run")
        runner = PipelineRunner(run_id="par-cont-run", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "par-continue.fail": "tr-fail",
            "seq-after.s": "tr-s",
        }

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(f"{sub_name}.{task.name}")
            if task.name == "fail":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "seq-after.s" in executed_tasks, "par-continue on_failure=continue 时 seq-after.s 应执行"


class TestDiamondDependencyInParallel:
    """测试 parallel 模式下的菱形依赖(a->b, a->c, b->d, c->d)"""

    @pytest.mark.asyncio
    async def test_diamond_parallel_respects_depends_on(self, db_engine, clean_db):
        """parallel 模式下菱形依赖仍应按 DAG 层级执行"""
        _setup_config()
        task_a = ResolvedTask(name="a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"])
        task_c = ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"])
        task_d = ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"])
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b, task_c, task_d],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="diamond-par")
        runner = PipelineRunner(run_id="diamond-par", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.{n}": f"tr-{n}" for n in ["a", "b", "c", "d"]}

        execution_order: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            execution_order.append(task.name)
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        idx = {n: execution_order.index(n) for n in ["a", "b", "c", "d"]}
        assert idx["a"] < idx["b"], "a 应在 b 之前"
        assert idx["a"] < idx["c"], "a 应在 c 之前"
        assert idx["b"] < idx["d"], "b 应在 d 之前"
        assert idx["c"] < idx["d"], "c 应在 d 之前"

    @pytest.mark.asyncio
    async def test_diamond_parallel_b_and_c_concurrent(self, db_engine, clean_db):
        """菱形中 b 和 c 无互相依赖,parallel 模式下应并发"""
        _setup_config()
        task_a = ResolvedTask(name="a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"])
        task_c = ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"])
        task_d = ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"])
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[task_a, task_b, task_c, task_d],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="diamond-bc-par")
        runner = PipelineRunner(run_id="diamond-bc-par", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.{n}": f"tr-{n}" for n in ["a", "b", "c", "d"]}

        start_times: dict[str, float] = {}
        inflight = 0
        max_inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal inflight, max_inflight
            start_times[task.name] = time.monotonic()
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # b 和 c 应并发执行(同时在运行中)
        assert max_inflight >= 2, f"菱形中 b/c 应并发,最大并发数={max_inflight}"


class TestSequentialWithinLevel:
    """测试 sequential 策略下同一 level 内 task 的串行行为"""

    @pytest.mark.asyncio
    async def test_sequential_tasks_run_one_by_one(self, db_engine, clean_db):
        """sequential 模式下,无 depends_on 的 task 也应串行执行"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="sequential"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="seq-level")
        runner = PipelineRunner(run_id="seq-level", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(4)}

        execution_start: dict[str, float] = {}
        execution_end: dict[str, float] = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            execution_start[task.name] = time.monotonic()
            await asyncio.sleep(0.02)
            execution_end[task.name] = time.monotonic()
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 串行执行时每个 task 在前一个结束后才开始
        for i in range(3):
            assert execution_end[f"t{i}"] <= execution_start[f"t{i + 1}"], f"t{i} 应在 t{i + 1} 之前完成"

    @pytest.mark.asyncio
    async def test_sequential_failure_stops_subsequent(self, db_engine, clean_db):
        """sequential 模式下,on_failure=fail 时 task 失败后后续 task 不执行"""
        _setup_config()
        tasks = [
            ResolvedTask(name="ok1", task_type="command", command="echo ok1"),
            ResolvedTask(name="fail", task_type="command", command="exit 1"),
            ResolvedTask(name="ok2", task_type="command", command="echo ok2"),
        ]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="sequential", on_failure="fail"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="seq-fail-stop")
        runner = PipelineRunner(run_id="seq-fail-stop", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.{n}": f"tr-{n}" for n in ["ok1", "fail", "ok2"]}

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(task.name)
            if task.name == "fail":
                return ExecutorResult(exit_code=1, stderr="fail")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "ok1" in executed_tasks, "ok1 应执行"
        assert "fail" in executed_tasks, "fail 应执行"
        assert "ok2" not in executed_tasks, "fail 后 ok2 不应执行"


class TestParallelWithMaxConcurrentTasksAndDependencies:
    """测试 parallel + max_concurrent_tasks + depends_on 三者混合的边缘场景"""

    @pytest.mark.asyncio
    async def test_parallel_with_limit_and_depends_on(self, db_engine, clean_db):
        """parallel + max_concurrent_tasks=2 + depends_on 时,排队等待 + 依赖都生效"""
        _setup_config()
        task_a = ResolvedTask(name="a", task_type="command", command="echo a")
        task_b = ResolvedTask(name="b", task_type="command", command="echo b")
        task_c = ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"])
        task_d = ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b"])
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=[task_a, task_b, task_c, task_d],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-limit-dep")
        runner = PipelineRunner(run_id="par-limit-dep", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.{n}": f"tr-{n}" for n in ["a", "b", "c", "d"]}

        execution_order: list[str] = []
        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            execution_order.append(task.name)
            await asyncio.sleep(0.02)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # a 和 b 同时启动(level 0),c 等 a 完成,d 等 b 完成
        assert max_inflight <= 2, f"max_concurrent_tasks=2 下并发不应超过2,实际={max_inflight}"
        idx = {n: execution_order.index(n) for n in ["a", "b", "c", "d"]}
        assert idx["a"] < idx["c"], "c 应在 a 之后"
        assert idx["b"] < idx["d"], "d 应在 b 之后"

    @pytest.mark.asyncio
    async def test_parallel_limit_with_many_tasks_all_complete(self, db_engine, clean_db):
        """parallel + max_concurrent_tasks=2 + 8 个 task,全部完成不丢失"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(8)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-many")
        runner = PipelineRunner(run_id="par-many", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(8)}

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(task.name)
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed_tasks) == 8, f"所有 8 个 task 应完成,实际执行了 {len(executed_tasks)} 个"
        assert set(executed_tasks) == {f"t{i}" for i in range(8)}


class TestCancelDuringQueueWait:
    """测试取消信号在 task 排队等待期间的行为"""

    @pytest.mark.asyncio
    async def test_cancel_stops_queued_tasks(self, db_engine, clean_db):
        """max_concurrent_tasks=1 时,取消后排队的 task 不应执行"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cancel-queue")
        runner = PipelineRunner(run_id="cancel-queue", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(4)}

        executed_tasks: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed_tasks.append(task.name)
            if task.name == "t0":
                runner._cancelled = True
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed_tasks) < 4, "取消后不应所有 task 都执行"


class TestEdgeCasesMaxConcurrentTasks:
    """测试 max_concurrent_tasks 的边界值"""

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_zero_falls_back_to_default(self, db_engine, clean_db):
        """max_concurrent_tasks=0 时应使用默认值 5"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=0),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="mc-zero")
        runner = PipelineRunner(run_id="mc-zero", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(6)}

        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.01)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # 默认值为 5,6 个 task 最多 5 个并发
        assert max_inflight <= 5, f"默认并发限制应为5,实际={max_inflight}"

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_none_falls_back_to_default(self, db_engine, clean_db):
        """max_concurrent_tasks=None 时应使用默认值 5"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=None),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="mc-none")
        runner = PipelineRunner(run_id="mc-none", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr{i}" for i in range(6)}

        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.01)
            inflight -= 1
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert max_inflight <= 5, f"None 时默认并发限制应为5,实际={max_inflight}"
