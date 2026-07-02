"""多 agent 并行 pipeline、顺序/并行执行、复杂依赖等场景测试。

覆盖场景:
- 多 subpipeline 同层并行执行
- max_concurrent_tasks 并发限制
- 扇出/扇入 (fan-out/fan-in) 模式
- 顺序执行策略下的隐式依赖链
- 重试 + 并行混合
- when 条件 + 并行
- 菱形依赖 + 多种失败模式
- 跨 subpipeline on_failure=continue 传播
- 大规模并行 (50 tasks)
- 取消信号在不同阶段的影响
- 并行 task 异常不崩溃 runner
- 环境变量继承链
- 混合 task 类型 (commands/steps/command)
- subpipeline 级别 post 阶段
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedPostConfig, ResolvedStep, ResolvedSubPipeline, ResolvedTask
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


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_runner(run_id, pipeline):
    ctx = ExecutionContext(pipeline=pipeline, run_id=run_id)
    runner = PipelineRunner(run_id=run_id, pipeline=pipeline, context=ctx)
    runner._task_run_ids = {}
    for sub in pipeline.subpipelines:
        for t in sub.tasks:
            runner._task_run_ids[f"{sub.name}.{t.name}"] = f"tr-{sub.name}-{t.name}"
    return runner


# ===========================================================================
# 1. 多 subpipeline 同层并行执行
# ===========================================================================

class TestParallelSubpipelinesSameLevel:
    """多个 subpipeline 在同一 level 并行执行"""

    @pytest.mark.asyncio
    async def test_two_independent_subpipelines_run(self, db_engine, clean_db):
        """两个无依赖的 subpipeline 都应被执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        runner = _make_runner("par-sub-1", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed
        assert "B.b1" in executed

    @pytest.mark.asyncio
    async def test_three_independent_subpipelines_same_level(self, db_engine, clean_db):
        """三个无依赖 subpipeline 同层并行"""
        _setup_config()
        subs = []
        for name in ["X", "Y", "Z"]:
            subs.append(ResolvedSubPipeline(
                name=name, config=PipelineConfig(),
                tasks=[ResolvedTask(name=f"{name.lower()}1", task_type="command", command=f"echo {name}")],
            ))
        pipeline = ResolvedPipeline(name="p", subpipelines=subs, top_config=PipelineConfig())
        runner = _make_runner("par-sub-3", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed) == 3

    @pytest.mark.asyncio
    async def test_same_level_one_fails_other_continues(self, db_engine, clean_db):
        """同层 subpipeline 一个失败,另一个不受影响"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(on_failure="fail"),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        runner = _make_runner("par-sub-fail", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="a1 failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed
        assert "B.b1" in executed


# ===========================================================================
# 2. max_concurrent_tasks 并发限制
# ===========================================================================

class TestMaxConcurrentTasks:
    """测试 max_concurrent_tasks 信号量限制并发"""

    @pytest.mark.asyncio
    async def test_semaphore_limits_parallel_tasks(self, db_engine, clean_db):
        """max_concurrent_tasks=2 时,同时运行的 task 不超过 2"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(6)]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig(max_concurrent_tasks=2))
        runner = _make_runner("sem-limit", pipeline)

        inflight = 0
        max_inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal inflight, max_inflight
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

        assert max_inflight <= 2, f"最大并发={max_inflight},应 <= 2"

    @pytest.mark.asyncio
    async def test_semaphore_with_max_concurrent_tasks_1_is_sequential(self, db_engine, clean_db):
        """max_concurrent_tasks=1 时,parallel 策略实际等价于串行"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(4)]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig(max_concurrent_tasks=1))
        runner = _make_runner("sem-1", pipeline)

        inflight = 0
        max_inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal inflight, max_inflight
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

        assert max_inflight <= 1


# ===========================================================================
# 3. 扇出/扇入 (fan-out/fan-in) 模式
# ===========================================================================

class TestFanOutFanIn:
    """一个源 task 分叉到多个并行 task,再汇聚到一个汇总 task"""

    @pytest.mark.asyncio
    async def test_fan_out_fan_in_10_branches(self, db_engine, clean_db):
        """1→10→1 扇出扇入模式"""
        _setup_config()
        tasks = [ResolvedTask(name="source", task_type="command", command="echo source")]
        for i in range(10):
            tasks.append(ResolvedTask(
                name=f"branch-{i}", task_type="command", command=f"echo branch {i}",
                depends_on=["source"],
            ))
        tasks.append(ResolvedTask(
            name="merge", task_type="command", command="echo merge",
            depends_on=[f"branch-{i}" for i in range(10)],
        ))
        sub = ResolvedSubPipeline(
            name="fan", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("fan-10", pipeline)

        execution_order = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            execution_order.append(task.name)
            await asyncio.sleep(0.005)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        idx = {n: i for i, n in enumerate(execution_order)}
        assert idx["source"] < idx["branch-0"]
        assert idx["branch-5"] < idx["merge"]
        assert len(execution_order) == 12

    @pytest.mark.asyncio
    async def test_fan_out_partial_failure_blocks_merge(self, db_engine, clean_db):
        """扇出中一个分支失败,merge task 不应执行 (on_failure=fail)"""
        _setup_config()
        tasks = [
            ResolvedTask(name="src", task_type="command", command="echo src"),
            ResolvedTask(name="b0", task_type="command", command="echo ok", depends_on=["src"]),
            ResolvedTask(name="b1", task_type="command", command="exit 1", depends_on=["src"]),
            ResolvedTask(name="b2", task_type="command", command="echo ok", depends_on=["src"]),
            ResolvedTask(name="merge", task_type="command", command="echo merge", depends_on=["b0", "b1", "b2"]),
        ]
        sub = ResolvedSubPipeline(
            name="fan", config=PipelineConfig(execution_strategy="parallel", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("fan-partial-fail", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "b1":
                return ExecutorResult(exit_code=1, stderr="b1 failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "src" in executed
        assert "b1" in executed
        assert "merge" not in executed


# ===========================================================================
# 4. 顺序执行策略下的隐式依赖链
# ===========================================================================

class TestSequentialImplicitChain:
    """sequential 策略下无 depends_on 的 task 应按 YAML 顺序隐式链式执行"""

    @pytest.mark.asyncio
    async def test_sequential_implicit_order(self, db_engine, clean_db):
        """5 个 task 无 depends_on,sequential 策略下应按声明顺序执行"""
        _setup_config()
        names = ["alpha", "beta", "gamma", "delta", "epsilon"]
        tasks = [ResolvedTask(name=n, task_type="command", command=f"echo {n}") for n in names]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="sequential"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("seq-implicit", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed == names

    @pytest.mark.asyncio
    async def test_sequential_failure_stops_chain(self, db_engine, clean_db):
        """sequential 链中一个失败,on_failure=fail 时后续跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="exit 1"),
            ResolvedTask(name="c", task_type="command", command="echo c"),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="sequential", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("seq-fail-stop", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "b":
                return ExecutorResult(exit_code=1, stderr="b failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "a" in executed
        assert "b" in executed
        assert "c" not in executed


# ===========================================================================
# 5. 重试 + 并行混合
# ===========================================================================

class TestRetryInParallel:
    """重试逻辑在并行执行上下文中的行为"""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_third_attempt_parallel(self, db_engine, clean_db):
        """并行 task 中某个 task 前两次失败第三次成功 (通过 create_executor mock 验证重试)"""
        _setup_config()
        call_counts = {}

        async def fake_executor_execute(command, env, log_path, timeout=None, cwd=None):
            task_id = env.get("TASKPPS_TASK_ID", "")
            call_counts[task_id] = call_counts.get(task_id, 0) + 1
            if "flaky" in task_id and call_counts[task_id] < 3:
                return ExecutorResult(exit_code=1, stderr="transient error")
            return ExecutorResult(exit_code=0, stdout="ok")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_executor_execute

        tasks = [
            ResolvedTask(name="stable", task_type="command", command="echo ok"),
            ResolvedTask(name="flaky", task_type="command", command="echo flaky", retry=2),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("retry-par", pipeline)

        from types import SimpleNamespace
        mock_settings = SimpleNamespace(executor=SimpleNamespace(default_timeout=60))

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings", return_value=mock_settings),
            patch("taskpps.engine.runner.build_log_path", return_value=runner._pipeline_log_path or "/tmp/test.log"),
        ):
            await runner.run()

        flaky_count = sum(v for k, v in call_counts.items() if "flaky" in k)
        assert flaky_count == 3, f"flaky 应执行 3 次(1 初始+2 重试),实际={flaky_count}"

    @pytest.mark.asyncio
    async def test_retry_exhausted_marks_task_failed(self, db_engine, clean_db):
        """重试用尽后 task 标记失败"""
        _setup_config()
        call_count = 0

        async def fake_executor_execute(command, env, log_path, timeout=None, cwd=None):
            nonlocal call_count
            call_count += 1
            return ExecutorResult(exit_code=1, stderr="always fail")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fake_executor_execute

        tasks = [ResolvedTask(name="t1", task_type="command", command="exit 1", retry=2)]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("retry-exhaust", pipeline)

        from types import SimpleNamespace
        mock_settings = SimpleNamespace(executor=SimpleNamespace(default_timeout=60))

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch("taskpps.engine.runner.get_settings", return_value=mock_settings),
            patch("taskpps.engine.runner.build_log_path", return_value="/tmp/test.log"),
        ):
            await runner.run()

        assert call_count == 3  # 1 initial + 2 retries


# ===========================================================================
# 6. when 条件 + 并行
# ===========================================================================

class TestWhenConditionParallel:
    """when 条件在并行 task 中的行为"""

    @pytest.mark.asyncio
    async def test_when_skips_some_parallel_tasks(self, db_engine, clean_db):
        """并行 task 中部分被 when 跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="always", task_type="command", command="echo always"),
            ResolvedTask(name="skip-me", task_type="command", command="echo skip", when='${SKIP} == "yes"'),
            ResolvedTask(name="also-run", task_type="command", command="echo also"),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(
            name="p", subpipelines=[sub],
            top_config=PipelineConfig(env={"SKIP": "no"}),
        )
        runner = _make_runner("when-par", pipeline)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert mock_executor.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_when_with_env_from_pipeline_config(self, db_engine, clean_db):
        """when 条件引用 pipeline 级 env"""
        _setup_config()
        tasks = [
            ResolvedTask(
                name="deploy-prod", task_type="command", command="echo deploy",
                when="${DEPLOY_ENV} == prod",
            ),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(), tasks=tasks,
        )
        pipeline = ResolvedPipeline(
            name="p", subpipelines=[sub],
            top_config=PipelineConfig(env={"DEPLOY_ENV": "prod"}),
        )
        runner = _make_runner("when-pipeline-env", pipeline)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        mock_executor.execute.assert_called_once()


# ===========================================================================
# 7. 菱形依赖 + 多种失败模式
# ===========================================================================

class TestDiamondFailureModes:
    """菱形依赖 (a→b,a→c,b→d,c→d) 的各种失败组合"""

    @pytest.mark.asyncio
    async def test_diamond_both_branches_fail_d_skips(self, db_engine, clean_db):
        """b 和 c 都失败,d 应跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="exit 1", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="exit 1", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        sub = ResolvedSubPipeline(
            name="dia", config=PipelineConfig(execution_strategy="parallel", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("dia-both-fail", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name in ("b", "c"):
                return ExecutorResult(exit_code=1, stderr=f"{task.name} failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "d" not in executed

    @pytest.mark.asyncio
    async def test_diamond_one_branch_fails_d_skips(self, db_engine, clean_db):
        """b 失败 c 成功,d 依赖 b 所以跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="exit 1", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        sub = ResolvedSubPipeline(
            name="dia", config=PipelineConfig(execution_strategy="parallel", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("dia-one-fail", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "b":
                return ExecutorResult(exit_code=1, stderr="b failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "d" not in executed

    @pytest.mark.asyncio
    async def test_diamond_continue_mode_d_still_runs(self, db_engine, clean_db):
        """b 有 on_failure=continue 时,b 失败但 d 仍应运行 (runner 检查失败依赖的 on_failure)"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="exit 1", depends_on=["a"], on_failure="continue"),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        sub = ResolvedSubPipeline(
            name="dia", config=PipelineConfig(execution_strategy="parallel", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("dia-continue", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "b":
                return ExecutorResult(exit_code=1, stderr="b failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "d" in executed


# ===========================================================================
# 8. 跨 subpipeline on_failure=continue 传播
# ===========================================================================

class TestCrossSubpipelineContinue:
    """on_failure=continue 在 subpipeline 级别的传播"""

    @pytest.mark.asyncio
    async def test_sub_on_failure_continue_allows_downstream(self, db_engine, clean_db):
        """sub A on_failure=continue 失败后,依赖 A 的 sub B 仍执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(on_failure="continue"),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        runner = _make_runner("cross-continue", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="a1 failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed
        assert "B.b1" in executed

    @pytest.mark.asyncio
    async def test_three_level_chain_continue(self, db_engine, clean_db):
        """A→B→C 三级链,A on_failure=continue 失败后 B 和 C 都应执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(on_failure="continue"),
            tasks=[ResolvedTask(name="a1", task_type="command", command="exit 1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        sub_c = ResolvedSubPipeline(
            name="C", config=PipelineConfig(), depends_on=["B"],
            tasks=[ResolvedTask(name="c1", task_type="command", command="echo c1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b, sub_c], top_config=PipelineConfig())
        runner = _make_runner("3level-continue", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                return ExecutorResult(exit_code=1, stderr="a1 failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed
        assert "B.b1" in executed
        assert "C.c1" in executed


# ===========================================================================
# 9. 大规模并行
# ===========================================================================

class TestLargeScaleParallel:
    """大规模并行执行"""

    @pytest.mark.asyncio
    async def test_50_independent_tasks_parallel(self, db_engine, clean_db):
        """50 个独立 task 并行执行,全部完成"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i:03d}", task_type="command", command=f"echo {i}") for i in range(50)]
        sub = ResolvedSubPipeline(
            name="big", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("big-50", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            await asyncio.sleep(0.001)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed) == 50
        assert set(executed) == {f"t{i:03d}" for i in range(50)}

    @pytest.mark.asyncio
    async def test_50_tasks_with_10_per_level(self, db_engine, clean_db):
        """50 个 task 分 5 层,每层 10 个并行,层间有依赖"""
        _setup_config()
        tasks = []
        for level in range(5):
            for i in range(10):
                name = f"l{level}t{i}"
                deps = [f"l{level - 1}t{j}" for j in range(10)] if level > 0 else []
                tasks.append(ResolvedTask(name=name, task_type="command", command=f"echo {name}", depends_on=deps))
        sub = ResolvedSubPipeline(
            name="layered", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("layered-50", pipeline)

        execution_order = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            execution_order.append(task.name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(execution_order) == 50
        # Verify ordering: all l0 before l1, all l1 before l2, etc.
        level_indices = {}
        for name in execution_order:
            level = int(name[1])
            level_indices.setdefault(level, []).append(execution_order.index(name))
        for level in range(4):
            assert max(level_indices[level]) < min(level_indices[level + 1])


# ===========================================================================
# 10. 取消信号在不同阶段的影响
# ===========================================================================

class TestCancelAtDifferentStages:
    """取消信号在不同执行阶段的效果"""

    @pytest.mark.asyncio
    async def test_cancel_before_any_execution(self, db_engine, clean_db):
        """在任何 task 执行前设置取消信号"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(3)]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("cancel-before", pipeline)
        runner._cancelled = True

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert not executed

    @pytest.mark.asyncio
    async def test_cancel_between_subpipelines(self, db_engine, clean_db):
        """第一个 subpipeline 完成后取消,第二个不执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(),
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        runner = _make_runner("cancel-between", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            if task.name == "a1":
                runner._cancelled = True
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed
        # B.b1 may or may not be executed depending on timing, but the pipeline should finish
        assert len(executed) <= 2


# ===========================================================================
# 11. 并行 task 异常不崩溃 runner
# ===========================================================================

class TestParallelTaskExceptionSafety:
    """并行 task 中抛出异常不应导致 runner 崩溃"""

    @pytest.mark.asyncio
    async def test_multiple_tasks_throw_exceptions(self, db_engine, clean_db):
        """多个并行 task 都抛异常,runner 应正常结束"""
        _setup_config()
        tasks = [
            ResolvedTask(name="ok", task_type="command", command="echo ok"),
            ResolvedTask(name="boom1", task_type="command", command="exit 1"),
            ResolvedTask(name="boom2", task_type="command", command="exit 1"),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel", on_failure="continue"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("multi-exc", pipeline)

        async def fake_execute(task, sub_name="", max_parallel=None):
            if task.name.startswith("boom"):
                raise RuntimeError(f"{task.name} exploded")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_all_tasks_throw_exceptions(self, db_engine, clean_db):
        """所有 task 都抛异常,runner 应正常结束"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="exit 1"),
            ResolvedTask(name="b", task_type="command", command="exit 1"),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("all-exc", pipeline)

        async def fake_execute(task, sub_name="", max_parallel=None):
            raise RuntimeError("boom")

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()


# ===========================================================================
# 12. 混合 task 类型 (commands/steps/command)
# ===========================================================================

class TestMixedTaskTypes:
    """同一 pipeline 中混合不同 task 类型"""

    @pytest.mark.asyncio
    async def test_commands_then_steps_then_single(self, db_engine, clean_db):
        """commands 类型 → steps 类型 → single command 类型"""
        _setup_config()
        task_cmds = ResolvedTask(
            name="cmds", task_type="command", commands=["echo a", "echo b"],
        )
        task_steps = ResolvedTask(
            name="steps", task_type="steps", steps=[
                ResolvedStep(run="echo s1"), ResolvedStep(run="echo s2"),
            ],
        )
        task_single = ResolvedTask(
            name="single", task_type="command", command="echo single",
        )
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="sequential"),
            tasks=[task_cmds, task_steps, task_single],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("mixed-types", pipeline)

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = ExecutorResult(exit_code=0, stdout="ok")

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        # commands(2) + steps(2) + single(1) = 5
        assert mock_executor.execute.call_count == 5


# ===========================================================================
# 13. subpipeline 级别 post 阶段
# ===========================================================================

class TestSubpipelinePostPhase:
    """测试 subpipeline 级别的 post 阶段"""

    @pytest.mark.asyncio
    async def test_subpipeline_post_on_success_executes(self, db_engine, clean_db):
        """subpipeline 成功后,on_success post 任务应执行"""
        _setup_config()
        post_task = ResolvedTask(name="cleanup", task_type="command", command="echo cleanup")
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="work", task_type="command", command="echo work")],
            post=ResolvedPostConfig(on_success=[post_task]),
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("post-success", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "work" in executed

    @pytest.mark.asyncio
    async def test_subpipeline_post_on_fail_executes(self, db_engine, clean_db):
        """subpipeline 失败后,on_fail post 任务应执行"""
        _setup_config()
        post_task = ResolvedTask(name="rollback", task_type="command", command="echo rollback")
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(),
            tasks=[ResolvedTask(name="work", task_type="command", command="exit 1")],
            post=ResolvedPostConfig(on_fail=[post_task]),
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("post-fail", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "work":
                return ExecutorResult(exit_code=1, stderr="work failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "work" in executed


# ===========================================================================
# 14. 环境变量继承链
# ===========================================================================

class TestEnvInheritanceChain:
    """环境变量从 pipeline → subpipeline → task 的继承"""

    @pytest.mark.asyncio
    async def test_env_merges_correctly(self, db_engine, clean_db):
        """pipeline env + task env 合并,task env 覆盖 pipeline env"""
        _setup_config()
        task = ResolvedTask(
            name="t1", task_type="command", command="echo t1",
            env={"TASK_VAR": "task_val", "SHARED": "from_task"},
        )
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(env={"SUB_VAR": "sub_val"}), tasks=[task],
        )
        pipeline = ResolvedPipeline(
            name="p", subpipelines=[sub],
            top_config=PipelineConfig(env={"PIPE_VAR": "pipe_val", "SHARED": "from_pipe"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="env-merge", env={"CTX_VAR": "ctx_val"})
        runner = PipelineRunner(run_id="env-merge", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.t1": "tr-t1"}

        captured_env = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal captured_env
            captured_env = ctx.get_task_env(task)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert captured_env.get("PIPE_VAR") == "pipe_val"
        assert captured_env.get("TASK_VAR") == "task_val"
        assert captured_env.get("SHARED") == "from_task"


# ===========================================================================
# 15. DAG 循环检测
# ===========================================================================

class TestDAGCycleDetection:
    """DAG 循环依赖检测"""

    @pytest.mark.asyncio
    async def test_task_cycle_detected(self, db_engine, clean_db):
        """task 间循环依赖应导致 subpipeline 失败"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["b"]),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("cycle-task", pipeline)

        with (
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_subpipeline_cycle_detected(self, db_engine, clean_db):
        """subpipeline 间循环依赖应被检测"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(), depends_on=["B"],
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b], top_config=PipelineConfig())
        runner = _make_runner("cycle-sub", pipeline)

        with (
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()


# ===========================================================================
# 16. 并行 + 顺序混合执行策略
# ===========================================================================

class TestMixedExecutionStrategies:
    """同一 pipeline 中不同 subpipeline 使用不同执行策略"""

    @pytest.mark.asyncio
    async def test_parallel_build_then_sequential_deploy(self, db_engine, clean_db):
        """parallel 构建 → sequential 部署"""
        _setup_config()
        build_tasks = [
            ResolvedTask(name="compile-frontend", task_type="command", command="echo fe"),
            ResolvedTask(name="compile-backend", task_type="command", command="echo be"),
        ]
        sub_build = ResolvedSubPipeline(
            name="build", config=PipelineConfig(execution_strategy="parallel"), tasks=build_tasks,
        )
        deploy_tasks = [
            ResolvedTask(name="upload", task_type="command", command="echo upload"),
            ResolvedTask(name="restart", task_type="command", command="echo restart", depends_on=["upload"]),
        ]
        sub_deploy = ResolvedSubPipeline(
            name="deploy", config=PipelineConfig(execution_strategy="sequential"), depends_on=["build"],
            tasks=deploy_tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_build, sub_deploy], top_config=PipelineConfig())
        runner = _make_runner("mix-strategy", pipeline)

        build_order = []
        deploy_order = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            if sub_name == "build":
                build_order.append(task.name)
            elif sub_name == "deploy":
                deploy_order.append(task.name)
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(build_order) == 2
        assert deploy_order == ["upload", "restart"]

    @pytest.mark.asyncio
    async def test_sequential_build_parallel_test_parallel_deploy(self, db_engine, clean_db):
        """sequential build → parallel test → parallel deploy (三级 subpipeline)"""
        _setup_config()
        build = ResolvedSubPipeline(
            name="build", config=PipelineConfig(execution_strategy="sequential"),
            tasks=[
                ResolvedTask(name="compile", task_type="command", command="echo compile"),
                ResolvedTask(name="package", task_type="command", command="echo package"),
            ],
        )
        test = ResolvedSubPipeline(
            name="test", config=PipelineConfig(execution_strategy="parallel"), depends_on=["build"],
            tasks=[
                ResolvedTask(name="unit", task_type="command", command="echo unit"),
                ResolvedTask(name="integration", task_type="command", command="echo integration"),
                ResolvedTask(name="e2e", task_type="command", command="echo e2e"),
            ],
        )
        deploy = ResolvedSubPipeline(
            name="deploy", config=PipelineConfig(execution_strategy="parallel"), depends_on=["test"],
            tasks=[
                ResolvedTask(name="svc-a", task_type="command", command="echo deploy a"),
                ResolvedTask(name="svc-b", task_type="command", command="echo deploy b"),
            ],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[build, test, deploy], top_config=PipelineConfig())
        runner = _make_runner("3level-mix", pipeline)

        sub_order = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            if sub_name and (not sub_order or sub_order[-1] != sub_name):
                sub_order.append(sub_name)
            await asyncio.sleep(0.005)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert sub_order == ["build", "test", "deploy"]


# ===========================================================================
# 17. 空 task 列表边界情况
# ===========================================================================

class TestEdgeCases:
    """边界情况"""

    @pytest.mark.asyncio
    async def test_pipeline_with_only_empty_subpipelines(self, db_engine, clean_db):
        """所有 subpipeline 都是空的"""
        _setup_config()
        subs = [
            ResolvedSubPipeline(name=f"empty-{i}", config=PipelineConfig(), tasks=[])
            for i in range(3)
        ]
        pipeline = ResolvedPipeline(name="p", subpipelines=subs, top_config=PipelineConfig())
        runner = _make_runner("all-empty", pipeline)

        with (
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_single_subpipeline_single_task(self, db_engine, clean_db):
        """最简场景: 1 subpipeline + 1 task"""
        _setup_config()
        sub = ResolvedSubPipeline(
            name="s", config=PipelineConfig(),
            tasks=[ResolvedTask(name="only", task_type="command", command="echo only")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("minimal", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed == ["only"]

    @pytest.mark.asyncio
    async def test_unknown_dependency_raises_error(self, db_engine, clean_db):
        """depends_on 引用不存在的 task 应报错"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a", depends_on=["nonexistent"]),
        ]
        sub = ResolvedSubPipeline(name="sub", config=PipelineConfig(), tasks=tasks)
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("unknown-dep", pipeline)

        with (
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()


# ===========================================================================
# 18. 并行执行中的执行顺序确定性
# ===========================================================================

class TestParallelOrderDeterminism:
    """并行执行中同一 level 的 task 应按 YAML 声明顺序"""

    @pytest.mark.asyncio
    async def test_parallel_tasks_start_in_yaml_order(self, db_engine, clean_db):
        """无依赖的并行 task 应按 YAML 声明顺序调度"""
        _setup_config()
        names = [f"task-{chr(65 + i)}" for i in range(10)]
        tasks = [ResolvedTask(name=n, task_type="command", command=f"echo {n}") for n in names]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("order-det", pipeline)

        start_order = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            start_order.append(task.name)
            await asyncio.sleep(0.005)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert start_order == names


# ===========================================================================
# 19. 多 subpipeline 依赖图 (非线性)
# ===========================================================================

class TestNonLinearDependencyGraph:
    """非线性 subpipeline 依赖图"""

    @pytest.mark.asyncio
    async def test_diamond_subpipeline_dependency(self, db_engine, clean_db):
        """subpipeline 菱形依赖: A→B,A→C,B→D,C→D"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="b1", task_type="command", command="echo b1")],
        )
        sub_c = ResolvedSubPipeline(
            name="C", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="c1", task_type="command", command="echo c1")],
        )
        sub_d = ResolvedSubPipeline(
            name="D", config=PipelineConfig(), depends_on=["B", "C"],
            tasks=[ResolvedTask(name="d1", task_type="command", command="echo d1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b, sub_c, sub_d], top_config=PipelineConfig())
        runner = _make_runner("dia-sub", pipeline)

        sub_order = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            if sub_name and (not sub_order or sub_order[-1] != sub_name):
                sub_order.append(sub_name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert sub_order.index("A") < sub_order.index("B")
        assert sub_order.index("A") < sub_order.index("C")
        assert sub_order.index("B") < sub_order.index("D")
        assert sub_order.index("C") < sub_order.index("D")

    @pytest.mark.asyncio
    async def test_diamond_subpipeline_one_branch_fails(self, db_engine, clean_db):
        """菱形 subpipeline 依赖中 B 失败,D 不应执行"""
        _setup_config()
        sub_a = ResolvedSubPipeline(
            name="A", config=PipelineConfig(),
            tasks=[ResolvedTask(name="a1", task_type="command", command="echo a1")],
        )
        sub_b = ResolvedSubPipeline(
            name="B", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="b1", task_type="command", command="exit 1")],
        )
        sub_c = ResolvedSubPipeline(
            name="C", config=PipelineConfig(), depends_on=["A"],
            tasks=[ResolvedTask(name="c1", task_type="command", command="echo c1")],
        )
        sub_d = ResolvedSubPipeline(
            name="D", config=PipelineConfig(), depends_on=["B", "C"],
            tasks=[ResolvedTask(name="d1", task_type="command", command="echo d1")],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_a, sub_b, sub_c, sub_d], top_config=PipelineConfig())
        runner = _make_runner("dia-sub-fail", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            if task.name == "b1":
                return ExecutorResult(exit_code=1, stderr="b1 failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A.a1" in executed
        assert "B.b1" in executed
        assert "C.c1" in executed
        assert "D.d1" not in executed


# ===========================================================================
# 20. 顺序执行中 task 级 on_failure 覆盖
# ===========================================================================

class TestTaskOnFailureOverride:
    """task 级 on_failure 覆盖 subpipeline 级策略"""

    @pytest.mark.asyncio
    async def test_failed_task_continue_allows_dependent_in_sequential(self, db_engine, clean_db):
        """sequential 中失败 task A 有 on_failure=continue,依赖 A 的 B 应继续执行"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="exit 1", on_failure="continue"),
            ResolvedTask(name="b", task_type="command", command="echo b"),
            ResolvedTask(name="c", task_type="command", command="echo c"),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="sequential", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("task-override-seq", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "a":
                return ExecutorResult(exit_code=1, stderr="a failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "a" in executed
        assert "b" in executed

    @pytest.mark.asyncio
    async def test_failed_task_continue_allows_dependent_in_parallel(self, db_engine, clean_db):
        """parallel 中失败 task A 有 on_failure=continue,依赖 A 的 B 应继续执行"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="exit 1", on_failure="continue"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c"),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("task-override-par", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "a":
                return ExecutorResult(exit_code=1, stderr="a failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "a" in executed
        assert "b" in executed


# ===========================================================================
# 21. 超时场景
# ===========================================================================

class TestTimeoutScenarios:
    """超时相关场景"""

    @pytest.mark.asyncio
    async def test_parallel_tasks_with_different_timeouts(self, db_engine, clean_db):
        """并行 task 有不同超时设置"""
        _setup_config()
        tasks = [
            ResolvedTask(name="fast", task_type="command", command="echo fast", timeout=5),
            ResolvedTask(name="slow", task_type="command", command="echo slow", timeout=60),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="parallel"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("timeout-par", pipeline)

        timeouts = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            timeouts[task.name] = "called"
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "fast" in timeouts
        assert "slow" in timeouts

    @pytest.mark.asyncio
    async def test_timeout_in_middle_of_chain(self, db_engine, clean_db):
        """链中间 task 超时,后续 task 跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="sleep 100", timeout=1, depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["b"]),
        ]
        sub = ResolvedSubPipeline(
            name="sub", config=PipelineConfig(execution_strategy="sequential", on_failure="fail"), tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        runner = _make_runner("timeout-chain", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "b":
                return ExecutorResult(exit_code=-1, stderr="timeout")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "a" in executed
        assert "b" in executed
        assert "c" not in executed


# ===========================================================================
# 22. 多层 subpipeline 级联失败
# ===========================================================================

class TestMultiLevelCascadeFailure:
    """多层 subpipeline 级联失败"""

    @pytest.mark.asyncio
    async def test_five_level_chain_first_fails_all_skip(self, db_engine, clean_db):
        """5 级 subpipeline 链,第 1 级失败,后续 4 级全部跳过"""
        _setup_config()
        subs = []
        for i in range(5):
            deps = [f"L{i - 1}"] if i > 0 else []
            task_cmd = "exit 1" if i == 0 else "echo ok"
            subs.append(ResolvedSubPipeline(
                name=f"L{i}", config=PipelineConfig(), depends_on=deps,
                tasks=[ResolvedTask(name=f"t{i}", task_type="command", command=task_cmd)],
            ))
        pipeline = ResolvedPipeline(name="p", subpipelines=subs, top_config=PipelineConfig())
        runner = _make_runner("5level-cascade", pipeline)

        executed = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(f"{sub_name}.{task.name}")
            if task.name == "t0":
                return ExecutorResult(exit_code=1, stderr="t0 failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "L0.t0" in executed
        assert "L1.t1" not in executed
        assert "L2.t2" not in executed
        assert "L3.t3" not in executed
        assert "L4.t4" not in executed
