"""针对 issue #131 修复的独立验证测试。

Issue #131: ``PipelineRunner.cancel()`` 存在竞态条件。
``cancel()`` 先执行异步数据库操作(``update_run_status`` /
``cancel_pending_tasks``),期间事件循环可以驱动 executor 完成,
``_execute_task`` 的 ``finally`` 块会把 executor 从
``_running_executors`` 中 ``pop`` 掉,导致后续 ``for ... in
_running_executors.items()`` 拿不到任何 executor,``executor.cancel()``
永远不会被调用。

期望修复:在 ``self._cancelled = True`` 之后,先快照
``self._running_executors``(``list(self._running_executors.values())``),
再执行任何可能 yield 的异步操作。

每个测试都设计了**确定性**的时序:通过 mock ``RunRepository`` 和
``TaskRunRepository`` 的方法,使其在 ``await`` 期间显式
``asyncio.sleep``,强制让出事件循环,给 executor 足够时间完成并
被 ``_execute_task`` 的 ``finally`` 块 ``pop`` 掉,稳定触发竞态。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedSubPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.executors.base import ExecutorResult
from taskpps.schemas.pipeline import OptionsYAML, PipelineConfig


def _setup_config():
    import taskpps.config as cfg

    if cfg._project_root is None:
        root = cfg.find_project_root()
        cfg.set_project_root(root)
    cfg._settings = None
    cfg.load_settings()


def make_pipeline(name: str = "test", tasks: list | None = None) -> ResolvedPipeline:
    if tasks is None:
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    return ResolvedPipeline(name=name, tasks=tasks, options=OptionsYAML())


class TestCancelRaceCondition:
    """验证 cancel() 在 executor 完成/被清理之前已捕获其引用。"""

    @pytest.mark.asyncio
    async def test_cancel_called_when_executor_completes_during_db_op(self, db_engine, clean_db):
        """核心场景:executor 在 cancel() 的 async DB 操作期间完成并被 pop。

        时序设计:
        - ``run()`` 启动后 0.05s 才调用 ``cancel()``,保证 executor 已
          进入 ``_running_executors``
        - mock ``RunRepository.update_run_status`` 在 ``await`` 期间
          sleep 0.15s(让出事件循环,驱动 executor 完成)
        - executor.execute() 实际 sleep 0.1s,完成时刻在 cancel 的
          ``update_run_status`` 期间
        - ``_execute_task`` 的 ``finally`` 块把 executor 从
          ``_running_executors`` 中 ``pop`` 出去
        - 修复前:cancel() 拿到的是空 dict,``executor.cancel`` 未被调用
        - 修复后:在 snapshot 阶段就拿到 executor 引用,``executor.cancel``
          被调用
        """
        _setup_config()
        task = ResolvedTask(name="build", task_type="command", command="sleep 1")
        pipeline = make_pipeline("race-single", [task])
        ctx = ExecutionContext(pipeline=pipeline, run_id="race-single-1")
        runner = PipelineRunner(run_id="race-single-1", pipeline=pipeline, context=ctx)

        executor_complete = asyncio.Event()

        async def fast_execute(command, env, log_path, timeout=None, cwd=None):
            # 0.1s 短于 cancel 的 update_run_status mock sleep 0.15s,
            # 保证 executor 会在 cancel 的 DB op 期间完成。
            await asyncio.sleep(0.1)
            executor_complete.set()
            return ExecutorResult(exit_code=0, stdout="done")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fast_execute
        mock_executor.cancel = AsyncMock()

        real_run_repo_cls = __import__("taskpps.db.repository", fromlist=["RunRepository"]).RunRepository
        real_task_repo_cls = __import__("taskpps.db.repository", fromlist=["TaskRunRepository"]).TaskRunRepository

        async def slow_update_run_status(self, *args, **kwargs):
            await asyncio.sleep(0.15)
            return await _real_update_run_status(self, *args, **kwargs)

        async def slow_cancel_pending_tasks(self, *args, **kwargs):
            await asyncio.sleep(0.01)
            return await _real_cancel_pending_tasks(self, *args, **kwargs)

        _real_update_run_status = real_run_repo_cls.update_run_status
        _real_cancel_pending_tasks = real_task_repo_cls.cancel_pending_tasks

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch.object(real_run_repo_cls, "update_run_status", new=slow_update_run_status),
            patch.object(
                real_task_repo_cls,
                "cancel_pending_tasks",
                new=slow_cancel_pending_tasks,
            ),
        ):
            run_task = asyncio.create_task(runner.run())
            # 轮询等待 executor 进入 _running_executors(最多 1s)
            for _ in range(100):
                if "build" in runner._running_executors:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Executor was not added to _running_executors within 1s")
            await runner.cancel()
            await executor_complete.wait()
            await run_task

        # 修复前这里会失败(executor 在 DB op 期间被 pop,cancel 没被调用)
        # 修复后这里会通过(快照保留了 executor 引用)
        assert mock_executor.cancel.called, (
            "Race condition: cancel() did not call executor.cancel() because "
            "executor was popped from _running_executors during the async DB "
            "operation. Snapshot of _running_executors must be taken before any "
            "await point in cancel()."
        )

    @pytest.mark.asyncio
    async def test_cancel_called_with_slow_executor_not_completing(self, db_engine, clean_db):
        """慢 executor(0.5s)在 DB op 期间也不完成:cancel 应被调用。

        Control case:无论是否有竞态,只要 executor 还在跑,cancel() 就
        应当被调用。这个 case 在修复前后都应通过。
        """
        _setup_config()
        task = ResolvedTask(name="build", task_type="command", command="sleep 1")
        pipeline = make_pipeline("race-slow", [task])
        ctx = ExecutionContext(pipeline=pipeline, run_id="race-slow-1")
        runner = PipelineRunner(run_id="race-slow-1", pipeline=pipeline, context=ctx)

        async def very_slow_execute(command, env, log_path, timeout=None, cwd=None):
            await asyncio.sleep(0.5)
            return ExecutorResult(exit_code=0, stdout="done")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = very_slow_execute
        mock_executor.cancel = AsyncMock()

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            run_task = asyncio.create_task(runner.run())
            for _ in range(100):
                if "build" in runner._running_executors:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Executor was not added to _running_executors within 1s")
            await runner.cancel()
            await run_task

        assert mock_executor.cancel.called, (
            "Slow executor that does not complete during DB ops should still have cancel() invoked."
        )

    @pytest.mark.asyncio
    async def test_cancel_no_running_executor_does_not_crash(self, db_engine, clean_db):
        """没有 running executor 时,cancel() 不应崩溃,也不应误调任何 cancel。"""
        _setup_config()
        task = ResolvedTask(name="fast", task_type="command", command="echo done")
        pipeline = make_pipeline("race-empty", [task])
        ctx = ExecutionContext(pipeline=pipeline, run_id="race-empty-1")
        runner = PipelineRunner(run_id="race-empty-1", pipeline=pipeline, context=ctx)

        async def fast_execute(command, env, log_path, timeout=None, cwd=None):
            return ExecutorResult(exit_code=0, stdout="done")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = fast_execute
        mock_executor.cancel = AsyncMock()

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
        ):
            run_task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.05)  # 等 task 完成
            # 此刻 _running_executors 已空,再调 cancel() 不应崩
            await runner.cancel()
            await run_task

        # 已经完成,不应该再 cancel
        assert not mock_executor.cancel.called, (
            "Cancel should not be invoked on executors that have already "
            "completed (no running executors at cancel() time)."
        )

    @pytest.mark.asyncio
    async def test_cancelled_flag_set_before_async_db_op(self, db_engine, clean_db):
        """``self._cancelled`` 在 async DB op 之前就被设置。

        验证:在 ``run()`` 启动 DB op 之后,由 ``cancel()`` 触发的
        ``update_run_status`` 调用中,``_cancelled`` 已经是 ``True``。
        区分方式:``run()`` 启动时调用 ``update_run_status(...,
        RunStatus.RUNNING, ...)``,``cancel()`` 调用
        ``update_run_status(..., RunStatus.CANCELLED)``,``_cancelled``
        标志必须在传 ``RunStatus.CANCELLED`` 的 DB op 开始之前是
        ``True``。
        """
        _setup_config()
        task = ResolvedTask(name="t", task_type="command", command="sleep 1")
        pipeline = make_pipeline("flag-check", [task])
        ctx = ExecutionContext(pipeline=pipeline, run_id="flag-check-1")
        runner = PipelineRunner(run_id="flag-check-1", pipeline=pipeline, context=ctx)

        async def slow_execute(command, env, log_path, timeout=None, cwd=None):
            await asyncio.sleep(0.1)
            return ExecutorResult(exit_code=0)

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = slow_execute
        mock_executor.cancel = AsyncMock()

        cancel_db_op_cancelled_state: list[bool] = []

        real_run_repo_cls = __import__("taskpps.db.repository", fromlist=["RunRepository"]).RunRepository
        _real_update_run_status = real_run_repo_cls.update_run_status

        # RunStatus 字符串常量,run() 传 "running",cancel() 传 "cancelled"。
        # 通过 status 参数判断是哪一处调过来的。
        async def recording_update_run_status(self, *args, **kwargs):
            status = kwargs.get("status", args[1] if len(args) > 1 else None)
            status_value = getattr(status, "value", status)
            if status_value == "cancelled":
                # 这是 cancel() 触发的 DB op,此时 _cancelled 必须是 True
                cancel_db_op_cancelled_state.append(runner._cancelled)
            return await _real_update_run_status(self, *args, **kwargs)

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch.object(real_run_repo_cls, "update_run_status", new=recording_update_run_status),
        ):
            run_task = asyncio.create_task(runner.run())
            for _ in range(100):
                if "t" in runner._running_executors:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Executor was not added to _running_executors within 1s")
            await runner.cancel()
            await run_task

        # 必须至少有一次 cancel() 触发的 DB op
        assert cancel_db_op_cancelled_state, (
            "Expected at least one update_run_status(..., CANCELLED) call from cancel()"
        )
        # 每次 cancel() 触发的 DB op 进入时,_cancelled 都必须是 True
        assert all(cancel_db_op_cancelled_state), (
            f"_cancelled flag must be set before async DB op initiated by cancel(), "
            f"observed: {cancel_db_op_cancelled_state}"
        )

    @pytest.mark.asyncio
    async def test_cancel_called_for_all_running_executors_in_parallel(self, db_engine, clean_db):
        """parallel 策略 + 多个 executor:cancel() 应对所有 running executor 调用 cancel。

        验证修复在多 executor 场景下也成立:即使有 2 个 executor 在
        running,cancel() 也应当对两者都调用 ``cancel()``,而不是只
        cancel 最后一个。
        """
        _setup_config()
        tasks = [
            ResolvedTask(name="t1", task_type="command", command="sleep 1"),
            ResolvedTask(name="t2", task_type="command", command="sleep 1"),
        ]
        sub = ResolvedSubPipeline(
            name="p",
            config=PipelineConfig(execution_strategy="parallel", max_concurrent_tasks=2),
            tasks=tasks,
        )
        pipeline = ResolvedPipeline(name="race-multi", subpipelines=[sub])
        ctx = ExecutionContext(pipeline=pipeline, run_id="race-multi-1")
        runner = PipelineRunner(run_id="race-multi-1", pipeline=pipeline, context=ctx)

        executor_complete = asyncio.Event()

        async def slow_execute(command, env, log_path, timeout=None, cwd=None):
            await asyncio.sleep(0.1)
            executor_complete.set()
            return ExecutorResult(exit_code=0, stdout="done")

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = slow_execute
        mock_executor.cancel = AsyncMock()

        real_run_repo_cls = __import__("taskpps.db.repository", fromlist=["RunRepository"]).RunRepository
        real_task_repo_cls = __import__("taskpps.db.repository", fromlist=["TaskRunRepository"]).TaskRunRepository

        async def slow_update_run_status(self, *args, **kwargs):
            await asyncio.sleep(0.15)
            return await _real_update_run_status(self, *args, **kwargs)

        async def slow_cancel_pending_tasks(self, *args, **kwargs):
            await asyncio.sleep(0.01)
            return await _real_cancel_pending_tasks(self, *args, **kwargs)

        _real_update_run_status = real_run_repo_cls.update_run_status
        _real_cancel_pending_tasks = real_task_repo_cls.cancel_pending_tasks

        with (
            patch("taskpps.engine.runner.create_executor", return_value=mock_executor),
            patch("taskpps.engine.runner.get_logs_dir"),
            patch("taskpps.engine.runner.get_event_bus"),
            patch.object(real_run_repo_cls, "update_run_status", new=slow_update_run_status),
            patch.object(
                real_task_repo_cls,
                "cancel_pending_tasks",
                new=slow_cancel_pending_tasks,
            ),
        ):
            run_task = asyncio.create_task(runner.run())
            # 轮询等待两个 executor 都进入 _running_executors
            for _ in range(100):
                if "t1" in runner._running_executors and "t2" in runner._running_executors:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Both executors were not added to _running_executors within 1s")
            await runner.cancel()
            await executor_complete.wait()
            await run_task

        # 由于只有一个 mock_executor 被两个 task 共享(因为 create_executor
        # 返回同一个),cancel() 应该被调用至少一次(每个 task 一次)。
        # 修复后:每个 running executor 都会被 cancel。
        # 修复前:可能为 0 次(都已被 pop)。
        assert mock_executor.cancel.call_count >= 1, (
            f"Expected executor.cancel() to be called at least once for "
            f"running executors, got {mock_executor.cancel.call_count} call(s). "
            f"Race condition: executor(s) popped from _running_executors "
            f"during async DB op."
        )
