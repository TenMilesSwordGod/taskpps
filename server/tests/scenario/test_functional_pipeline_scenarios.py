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


class TestRealWorldPipelineScenarios:
    """真实世界 pipeline 场景测试 — 模拟 CI/CD、部署、测试等实际使用场景"""

    @pytest.mark.asyncio
    async def test_ci_cd_full_pipeline(self, db_engine, clean_db):
        """CI/CD 完整流水线: lint → build → test → deploy,每步有依赖"""
        _setup_config()
        tasks = [
            ResolvedTask(name="lint", task_type="command", command="echo linting..."),
            ResolvedTask(name="build", task_type="command", command="echo building...", depends_on=["lint"]),
            ResolvedTask(name="unit-test", task_type="command", command="echo unit tests...", depends_on=["build"]),
            ResolvedTask(
                name="integration-test", task_type="command", command="echo integration tests...", depends_on=["build"]
            ),
            ResolvedTask(
                name="deploy-staging",
                task_type="command",
                command="echo deploying staging...",
                depends_on=["unit-test", "integration-test"],
            ),
            ResolvedTask(
                name="smoke-test", task_type="command", command="echo smoke testing...", depends_on=["deploy-staging"]
            ),
            ResolvedTask(
                name="deploy-prod", task_type="command", command="echo deploying prod...", depends_on=["smoke-test"]
            ),
        ]
        sub = ResolvedSubPipeline(
            name="ci-cd",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="full-ci", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="ci-cd-1")
        runner = PipelineRunner(run_id="ci-cd-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"ci-cd.{t.name}": f"tr-{t.name}" for t in tasks}

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

        idx = {n: execution_order.index(n) for n in execution_order}
        assert idx["lint"] < idx["build"]
        assert idx["build"] < idx["unit-test"]
        assert idx["build"] < idx["integration-test"]
        assert idx["unit-test"] < idx["deploy-staging"]
        assert idx["integration-test"] < idx["deploy-staging"]
        assert idx["deploy-staging"] < idx["smoke-test"]
        assert idx["smoke-test"] < idx["deploy-prod"]

    @pytest.mark.asyncio
    async def test_microservice_deploy_with_shared_dependency(self, db_engine, clean_db):
        """微服务部署: 共享依赖库构建后,3 个服务并行部署"""
        _setup_config()
        tasks = [
            ResolvedTask(name="build-lib", task_type="command", command="echo building shared lib..."),
            ResolvedTask(
                name="deploy-auth", task_type="command", command="echo deploying auth...", depends_on=["build-lib"]
            ),
            ResolvedTask(
                name="deploy-api", task_type="command", command="echo deploying api...", depends_on=["build-lib"]
            ),
            ResolvedTask(
                name="deploy-gateway",
                task_type="command",
                command="echo deploying gateway...",
                depends_on=["build-lib"],
            ),
            ResolvedTask(
                name="health-check",
                task_type="command",
                command="echo health check...",
                depends_on=["deploy-auth", "deploy-api", "deploy-gateway"],
            ),
        ]
        sub = ResolvedSubPipeline(
            name="micro-deploy",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="micro-1")
        runner = PipelineRunner(run_id="micro-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"micro-deploy.{t.name}": f"tr-{t.name}" for t in tasks}

        start_times: dict[str, float] = {}
        end_times: dict[str, float] = {}
        max_inflight = 0
        inflight = 0

        async def fake_execute(task, sub_name="", max_parallel=None):
            nonlocal max_inflight, inflight
            start_times[task.name] = time.monotonic()
            inflight += 1
            if inflight > max_inflight:
                max_inflight = inflight
            await asyncio.sleep(0.02)
            inflight -= 1
            end_times[task.name] = time.monotonic()
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert start_times["build-lib"] < start_times["deploy-auth"]
        assert start_times["build-lib"] < start_times["deploy-api"]
        assert start_times["build-lib"] < start_times["deploy-gateway"]
        assert end_times["build-lib"] <= start_times["deploy-auth"]
        assert end_times["build-lib"] <= start_times["deploy-api"]
        assert end_times["build-lib"] <= start_times["deploy-gateway"]
        assert max_inflight >= 3, f"3 个微服务应并行部署,最大并发={max_inflight}"

    @pytest.mark.asyncio
    async def test_cascade_failure_with_continue(self, db_engine, clean_db):
        """级联失败场景: A→B→C→D,B 失败但 on_failure=continue,验证 C/D 行为"""
        _setup_config()
        tasks = [
            ResolvedTask(name="A", task_type="command", command="echo A"),
            ResolvedTask(name="B", task_type="command", command="exit 1", depends_on=["A"]),
            ResolvedTask(name="C", task_type="command", command="echo C", depends_on=["B"], on_failure="continue"),
            ResolvedTask(name="D", task_type="command", command="echo D", depends_on=["C"]),
        ]
        sub = ResolvedSubPipeline(
            name="cascade",
            config=PipelineConfig(execution_strategy="sequential", on_failure="continue"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cascade-1")
        runner = PipelineRunner(run_id="cascade-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"cascade.{n}": f"tr-{n}" for n in ["A", "B", "C", "D"]}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "B":
                return ExecutorResult(exit_code=1, stderr="B failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A" in executed
        assert "B" in executed
        assert "C" not in executed, "B 失败后依赖 B 的 C 应被跳过"
        assert "D" not in executed, "C 被跳过后依赖 C 的 D 不应执行"

    @pytest.mark.asyncio
    async def test_multi_subpipeline_complex_chain(self, db_engine, clean_db):
        """复杂多 subpipeline 依赖链: build(pipeline) → test-parallel(pipeline) → deploy(pipeline)
        其中 test-parallel 内部 3 个 task 并行执行"""
        _setup_config()
        # build: sequential
        build_tasks = [
            ResolvedTask(name="compile", task_type="command", command="echo compile"),
            ResolvedTask(name="package", task_type="command", command="echo package", depends_on=["compile"]),
        ]
        sub_build = ResolvedSubPipeline(
            name="build",
            config=PipelineConfig(execution_strategy="sequential"),
            tasks=build_tasks,
        )

        # test: parallel
        test_tasks = [
            ResolvedTask(name="unit", task_type="command", command="echo unit"),
            ResolvedTask(name="integration", task_type="command", command="echo integration"),
            ResolvedTask(name="e2e", task_type="command", command="echo e2e"),
        ]
        sub_test = ResolvedSubPipeline(
            name="test",
            config=PipelineConfig(execution_strategy="parallel"),
            depends_on=["build"],
            tasks=test_tasks,
        )

        # deploy: sequential
        deploy_tasks = [
            ResolvedTask(name="upload", task_type="command", command="echo upload"),
            ResolvedTask(name="restart", task_type="command", command="echo restart", depends_on=["upload"]),
        ]
        sub_deploy = ResolvedSubPipeline(
            name="deploy",
            config=PipelineConfig(execution_strategy="sequential"),
            depends_on=["test"],
            tasks=deploy_tasks,
        )

        pipeline = ResolvedPipeline(
            name="complex", subpipelines=[sub_build, sub_test, sub_deploy], top_config=PipelineConfig()
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="complex-1")
        runner = PipelineRunner(run_id="complex-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {}
        for sub_name, task_list in [("build", build_tasks), ("test", test_tasks), ("deploy", deploy_tasks)]:
            for t in task_list:
                runner._task_run_ids[f"{sub_name}.{t.name}"] = f"tr-{t.name}"

        sub_execution_order: list[str] = []
        test_start_times: dict[str, float] = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            if sub_name and (not sub_execution_order or sub_execution_order[-1] != sub_name):
                sub_execution_order.append(sub_name)
            if sub_name == "test":
                test_start_times[task.name] = time.monotonic()
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert sub_execution_order.index("build") < sub_execution_order.index("test")
        assert sub_execution_order.index("test") < sub_execution_order.index("deploy")
        # test 内部 3 个 task 应并行
        times = list(test_start_times.values())
        if len(times) >= 3:
            spread = max(times) - min(times)
            assert spread < 0.005, f"test 内部 3 个 task 应并行,时间差={spread:.4f}s"

    @pytest.mark.asyncio
    async def test_partial_failure_in_parallel_subpipeline(self, db_engine, clean_db):
        """parallel subpipeline 中部分 task 失败,验证 on_failure=continue 时其他 task 继续"""
        _setup_config()
        tasks = [
            ResolvedTask(name="fast", task_type="command", command="echo fast"),
            ResolvedTask(name="fail-fast", task_type="command", command="exit 1"),
            ResolvedTask(name="slow", task_type="command", command="echo slow"),
        ]
        sub = ResolvedSubPipeline(
            name="mixed",
            config=PipelineConfig(execution_strategy="parallel", on_failure="continue"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="partial-1")
        runner = PipelineRunner(run_id="partial-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"mixed.{n}": f"tr-{n}" for n in ["fast", "fail-fast", "slow"]}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "fail-fast":
                return ExecutorResult(exit_code=1, stderr="failed")
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "fast" in executed
        assert "fail-fast" in executed
        assert "slow" in executed

    @pytest.mark.asyncio
    async def test_timeout_cascades_to_dependent_tasks(self, db_engine, clean_db):
        """超时场景: task A 超时失败后,依赖 A 的 task B 不应执行"""
        _setup_config()
        tasks = [
            ResolvedTask(name="A", task_type="command", command="sleep 100", timeout=1),
            ResolvedTask(name="B", task_type="command", command="echo B", depends_on=["A"]),
        ]
        sub = ResolvedSubPipeline(
            name="timeout-test",
            config=PipelineConfig(execution_strategy="sequential", on_failure="fail"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="timeout-1")
        runner = PipelineRunner(run_id="timeout-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"timeout-test.A": "tr-A", "timeout-test.B": "tr-B"}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "A":
                return ExecutorResult(exit_code=-1, stderr="timeout")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "A" in executed
        assert "B" not in executed, "A 超时失败后 B 不应执行"

    @pytest.mark.asyncio
    async def test_empty_pipeline_runs_successfully(self, db_engine, clean_db):
        """空 pipeline(无 task)应成功完成"""
        _setup_config()
        sub = ResolvedSubPipeline(
            name="empty",
            config=PipelineConfig(),
            tasks=[],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="empty-1")
        runner = PipelineRunner(run_id="empty-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {}

        with (
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

    @pytest.mark.asyncio
    async def test_single_task_pipeline(self, db_engine, clean_db):
        """单 task pipeline 应正常执行"""
        _setup_config()
        task = ResolvedTask(name="only", task_type="command", command="echo only")
        sub = ResolvedSubPipeline(
            name="single",
            config=PipelineConfig(),
            tasks=[task],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="single-1")
        runner = PipelineRunner(run_id="single-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"single.only": "tr-only"}

        executed: list[str] = []

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
    async def test_many_independent_tasks_all_execute(self, db_engine, clean_db):
        """20 个独立 task 全部执行(无依赖)"""
        _setup_config()
        tasks = [ResolvedTask(name=f"task-{i:02d}", task_type="command", command=f"echo {i}") for i in range(20)]
        sub = ResolvedSubPipeline(
            name="many",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="many-1")
        runner = PipelineRunner(run_id="many-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"many.task-{i:02d}": f"tr-{i}" for i in range(20)}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            await asyncio.sleep(0.005)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed) == 20
        assert set(executed) == {f"task-{i:02d}" for i in range(20)}

    @pytest.mark.asyncio
    async def test_deep_dependency_chain(self, db_engine, clean_db):
        """10 层深度依赖链: t0→t1→t2→...→t9"""
        _setup_config()
        tasks = [ResolvedTask(name="t0", task_type="command", command="echo t0")]
        for i in range(1, 10):
            tasks.append(
                ResolvedTask(name=f"t{i}", task_type="command", command=f"echo t{i}", depends_on=[f"t{i - 1}"])
            )
        sub = ResolvedSubPipeline(
            name="deep",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="deep-1")
        runner = PipelineRunner(run_id="deep-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"deep.t{i}": f"tr-{i}" for i in range(10)}

        execution_order: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            execution_order.append(task.name)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        for i in range(9):
            assert execution_order.index(f"t{i}") < execution_order.index(f"t{i + 1}"), f"t{i} 应在 t{i + 1} 之前"

    @pytest.mark.asyncio
    async def test_diamond_with_parallel_and_failure(self, db_engine, clean_db):
        """菱形依赖 + parallel + 部分失败: a→b,a→c,b→d,c→d,b 失败时 d 是否跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="exit 1", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        sub = ResolvedSubPipeline(
            name="diamond",
            config=PipelineConfig(execution_strategy="parallel", on_failure="fail"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="diamond-fail-1")
        runner = PipelineRunner(run_id="diamond-fail-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"diamond.{n}": f"tr-{n}" for n in ["a", "b", "c", "d"]}

        executed: list[str] = []

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
        assert "d" not in executed, "b 失败了,d 依赖 b 不应执行"

    @pytest.mark.asyncio
    async def test_cross_subpipeline_failure_propagation(self, db_engine, clean_db):
        """跨 subpipeline 失败传播: build(fail) → test → deploy,build 失败后 test 和 deploy 都跳过"""
        _setup_config()
        sub_build = ResolvedSubPipeline(
            name="build",
            config=PipelineConfig(execution_strategy="sequential", on_failure="fail"),
            tasks=[ResolvedTask(name="compile", task_type="command", command="exit 1")],
        )
        sub_test = ResolvedSubPipeline(
            name="test",
            config=PipelineConfig(execution_strategy="parallel"),
            depends_on=["build"],
            tasks=[
                ResolvedTask(name="unit", task_type="command", command="echo unit"),
                ResolvedTask(name="e2e", task_type="command", command="echo e2e"),
            ],
        )
        sub_deploy = ResolvedSubPipeline(
            name="deploy",
            config=PipelineConfig(execution_strategy="sequential"),
            depends_on=["test"],
            tasks=[ResolvedTask(name="push", task_type="command", command="echo push")],
        )
        pipeline = ResolvedPipeline(
            name="p", subpipelines=[sub_build, sub_test, sub_deploy], top_config=PipelineConfig()
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="cross-fail-1")
        runner = PipelineRunner(run_id="cross-fail-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "build.compile": "tr-compile",
            "test.unit": "tr-unit",
            "test.e2e": "tr-e2e",
            "deploy.push": "tr-push",
        }

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            name = f"{sub_name}.{task.name}"
            executed.append(name)
            if task.name == "compile":
                return ExecutorResult(exit_code=1, stderr="compile failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "build.compile" in executed
        assert "test.unit" not in executed
        assert "test.e2e" not in executed
        assert "deploy.push" not in executed

    @pytest.mark.asyncio
    async def test_mixed_strategy_subpipelines_parallel_then_sequential(self, db_engine, clean_db):
        """混合策略 subpipeline: parallel(deploy多服务) → sequential(验证)"""
        _setup_config()
        sub_deploy = ResolvedSubPipeline(
            name="deploy",
            config=PipelineConfig(execution_strategy="parallel"),
            tasks=[
                ResolvedTask(name="svc-a", task_type="command", command="echo deploy A"),
                ResolvedTask(name="svc-b", task_type="command", command="echo deploy B"),
                ResolvedTask(name="svc-c", task_type="command", command="echo deploy C"),
            ],
        )
        sub_verify = ResolvedSubPipeline(
            name="verify",
            config=PipelineConfig(execution_strategy="sequential"),
            depends_on=["deploy"],
            tasks=[
                ResolvedTask(name="check-a", task_type="command", command="echo check A"),
                ResolvedTask(name="check-b", task_type="command", command="echo check B", depends_on=["check-a"]),
            ],
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub_deploy, sub_verify], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="mix-strat-1")
        runner = PipelineRunner(run_id="mix-strat-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {
            "deploy.svc-a": "tr-a",
            "deploy.svc-b": "tr-b",
            "deploy.svc-c": "tr-c",
            "verify.check-a": "tr-ka",
            "verify.check-b": "tr-kb",
        }

        sub_order: list[str] = []
        deploy_start: dict[str, float] = {}

        async def fake_execute(task, sub_name="", max_parallel=None):
            if sub_name and (not sub_order or sub_order[-1] != sub_name):
                sub_order.append(sub_name)
            if sub_name == "deploy":
                deploy_start[task.name] = time.monotonic()
            await asyncio.sleep(0.01)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert sub_order.index("deploy") < sub_order.index("verify")
        assert len(deploy_start) == 3

    @pytest.mark.asyncio
    async def test_cancel_during_parallel_execution(self, db_engine, clean_db):
        """parallel 执行中取消: 5 个 task,第 2 个完成后取消,验证后续 task 行为"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(5)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cancel-par-1")
        runner = PipelineRunner(run_id="cancel-par-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr-{i}" for i in range(5)}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "t1":
                runner._cancelled = True
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert len(executed) < 5, f"取消后不应所有 task 都执行,实际执行了 {len(executed)} 个"

    @pytest.mark.asyncio
    async def test_cancel_while_parallel_tasks_pending(self, db_engine, clean_db):
        """parallel 执行中取消时,正在 pending 的 task 应被取消,未调度的 task 不应执行。

        max_concurrent_tasks=3,同时启动 t0/t1/t2。t1 完成后设置 cancel 信号,
        此时 t0/t2 仍在运行(处于 pending set 中),runner 应取消它们,
        并且不再调度 t3/t4。
        """
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(5)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=3),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cancel-pending-1")
        runner = PipelineRunner(run_id="cancel-pending-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr-{i}" for i in range(5)}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "t1":
                runner._cancelled = True
                return ExecutorResult(exit_code=0)
            # t0/t2 稍微 sleep,确保 t1 完成并触发 cancel 时它们仍在 pending
            await asyncio.sleep(0.2)
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "t3" not in executed, "取消后未调度的 t3 不应执行"
        assert "t4" not in executed, "取消后未调度的 t4 不应执行"
        assert len(executed) <= 3, f"最多只能有 3 个 task 进入执行,实际 {len(executed)} 个"

    @pytest.mark.asyncio
    async def test_cancel_before_parallel_task_acquires_semaphore(self, db_engine, clean_db):
        """cancel 信号在 task 获取并发槽位前已设置,task 应直接跳过不执行。"""
        _setup_config()
        tasks = [ResolvedTask(name=f"t{i}", task_type="command", command=f"echo {i}") for i in range(3)]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=1),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="cancel-pre-1")
        runner = PipelineRunner(run_id="cancel-pre-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"sub.t{i}": f"tr-{i}" for i in range(3)}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            return ExecutorResult(exit_code=0)

        runner._cancelled = True
        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert not executed, f"取消信号已设置,所有 parallel task 都不应执行,实际 {executed}"

    @pytest.mark.asyncio
    async def test_parallel_execution_handles_task_exception(self, db_engine, clean_db):
        """parallel subpipeline 中某个 task 抛异常,不应导致 runner 崩溃,其它 task 仍应完成。"""
        _setup_config()
        tasks = [
            ResolvedTask(name="ok", task_type="command", command="echo ok"),
            ResolvedTask(name="boom", task_type="command", command="exit 1"),
        ]
        sub = ResolvedSubPipeline(
            name="sub",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="par-exc-1")
        runner = PipelineRunner(run_id="par-exc-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {"sub.ok": "tr-ok", "sub.boom": "tr-boom"}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name == "boom":
                raise RuntimeError("unexpected boom")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert "ok" in executed
        assert "boom" in executed

    @pytest.mark.asyncio
    async def test_rapid_success_failure_success(self, db_engine, clean_db):
        """快速成功-失败-成功交替: A(ok) → B(fail, continue) → C(ok) → D(fail, continue) → E(ok); 失败依赖级联跳过"""
        _setup_config()
        tasks = [
            ResolvedTask(name="A", task_type="command", command="echo A"),
            ResolvedTask(name="B", task_type="command", command="exit 1", depends_on=["A"]),
            ResolvedTask(name="C", task_type="command", command="echo C", depends_on=["B"]),
            ResolvedTask(name="D", task_type="command", command="exit 1", depends_on=["C"]),
            ResolvedTask(name="E", task_type="command", command="echo E", depends_on=["D"]),
        ]
        sub = ResolvedSubPipeline(
            name="alternating",
            config=PipelineConfig(execution_strategy="sequential", on_failure="continue"),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="p", subpipelines=[sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="alt-1")
        runner = PipelineRunner(run_id="alt-1", pipeline=pipeline, context=ctx)
        runner._task_run_ids = {f"alternating.{n}": f"tr-{n}" for n in ["A", "B", "C", "D", "E"]}

        executed: list[str] = []

        async def fake_execute(task, sub_name="", max_parallel=None):
            executed.append(task.name)
            if task.name in ("B", "D"):
                return ExecutorResult(exit_code=1, stderr=f"{task.name} failed")
            return ExecutorResult(exit_code=0)

        with (
            patch.object(runner, "_execute_task", side_effect=fake_execute),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            await runner.run()

        assert executed == ["A", "B"], "B 失败后依赖 B 的下游 task 应级联跳过"
