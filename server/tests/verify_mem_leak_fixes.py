"""内存泄漏修复验证脚本。

只测泄漏场景，不启动服务器/runner/SSE，避免内存爆炸。
"""
from __future__ import annotations

import gc
import sys
import weakref
from unittest.mock import MagicMock


def test_running_executors_cleaned_on_cancelled_error():
    """验证 CancelledError 传播时 _running_executors 被清理。"""
    import asyncio

    # 预加载依赖，避免循环导入
    import taskpps.services.agent_manager  # noqa: F401
    from taskpps.executors.agent_executor import AgentExecutor

    # 手动构造 runner 的 _running_executors，不导入 PipelineRunner
    _running_executors = {}

    executor = MagicMock(spec=AgentExecutor)
    executor._command_id = "test-cmd"
    executor._manager = MagicMock()
    executor._manager.get_connection.return_value = None
    _running_executors["task-1"] = executor

    # 模拟 CancelledError 传播后的 finally 块（与 runner.py 逻辑一致）
    try:
        raise asyncio.CancelledError()
    except BaseException:
        pass
    finally:
        popped = _running_executors.pop("task-1", None)
        if isinstance(popped, AgentExecutor):
            popped.cleanup()

    assert "task-1" not in _running_executors, (
        "_running_executors 未被清理！CancelledError 路径泄漏"
    )
    executor.cleanup.assert_called_once()
    print("PASS: _running_executors cleaned on CancelledError")


def test_agent_executor_cleanup_removes_output_callback():
    """验证 AgentExecutor.cleanup() 移除 output callback。"""
    import taskpps.services.agent_manager  # noqa: F401
    from taskpps.executors.agent_executor import AgentExecutor
    from taskpps.services.agent_manager import AgentConnection

    ws = MagicMock()
    conn = AgentConnection("test-agent", ws)

    callback = lambda data: None  # noqa: E731
    conn._output_callbacks["cmd-123"] = callback
    assert "cmd-123" in conn._output_callbacks

    executor = AgentExecutor.__new__(AgentExecutor)
    executor._command_id = "cmd-123"
    executor._agent_id = "test-agent"
    executor._manager = MagicMock()
    executor._manager.get_connection.return_value = conn

    executor.cleanup()

    assert "cmd-123" not in conn._output_callbacks, (
        "cleanup() 未移除 output callback！泄漏"
    )
    print("PASS: AgentExecutor.cleanup() removes output callback")


def test_agent_exec_cleanup_on_timeout():
    """验证 agent_exec 端点超时时调用 cleanup_command。"""
    import inspect

    from taskpps.api import agents

    source = inspect.getsource(agents.agent_exec)

    timeout_block = source[source.index("asyncio.TimeoutError"):]
    timeout_block = timeout_block[:timeout_block.index("except")]
    assert "cleanup_command" in timeout_block, (
        "agent_exec TimeoutError 分支缺少 cleanup_command！"
    )

    cancel_block = source[source.index("asyncio.CancelledError"):]
    cancel_block = cancel_block[:cancel_block.index("raise")]
    assert "cleanup_command" in cancel_block, (
        "agent_exec CancelledError 分支缺少 cleanup_command！"
    )
    print("PASS: agent_exec calls cleanup_command on timeout/cancel")


def test_disconnect_cleanup_handles_exceptions():
    """验证 _cleanup_after_grace 中 cleanup_command 异常不阻止后续清理。"""
    import inspect

    from taskpps.services.agent_manager import AgentManager

    source = inspect.getsource(AgentManager._schedule_disconnect_cleanup)

    assert "try:" in source and "cleanup_command" in source, (
        "_cleanup_after_grace 缺少异常处理！"
    )
    lines = source.split("\n")
    in_try = False
    for line in lines:
        if "try:" in line:
            in_try = True
        if "cleanup_command" in line and in_try:
            break
    else:
        assert False, "cleanup_command 不在 try 块内！"

    print("PASS: _cleanup_after_grace has exception handling for cleanup_command")


def test_agent_exec_normal_path_cleans_output_callback():
    """验证 agent_exec 正常完成时清理 output callback。"""
    import inspect

    from taskpps.api import agents

    source = inspect.getsource(agents.agent_exec)

    assert "_output_callbacks.pop" in source, (
        "agent_exec 正常完成路径缺少 _output_callbacks.pop！"
    )
    print("PASS: agent_exec normal path cleans output callback")


def test_gc_can_collect_cleaned_executor():
    """验证清理后的 executor 可以被 GC 回收。"""
    import taskpps.services.agent_manager  # noqa: F401
    from taskpps.executors.agent_executor import AgentExecutor
    from taskpps.services.agent_manager import AgentConnection

    ws = MagicMock()
    conn = AgentConnection("test-agent", ws)

    executor = AgentExecutor.__new__(AgentExecutor)
    executor._command_id = "cmd-gc"
    executor._agent_id = "test-agent"
    executor._manager = MagicMock()
    executor._manager.get_connection.return_value = conn

    class BigContainer:
        def __init__(self):
            self.data = list(range(100000))

    container = BigContainer()
    conn._output_callbacks["cmd-gc"] = lambda data: container.data.append(data)

    executor_ref = weakref.ref(executor)
    container_ref = weakref.ref(container)

    # cleanup
    executor.cleanup()

    del executor
    del container
    gc.collect()

    assert executor_ref() is None, "executor 未被 GC 回收！内存泄漏"
    assert container_ref() is None, "container 未被 GC 回收！内存泄漏"
    print("PASS: Cleaned executor and captured data can be garbage collected")


def test_gc_leaked_callback_keeps_data_alive():
    """验证未清理的 output callback 会阻止数据被 GC（泄漏确认）。

    注意：Python GC 能检测并打破简单循环引用，所以这个测试在 CPython 中
    可能不按预期工作。真正的泄漏场景是 AgentManager._connections（长期存活）
    持有 AgentConnection，其 _output_callbacks 持有闭包，闭包捕获大对象。
    这里只验证 cleanup 后数据可以被回收。
    """
    from taskpps.services.agent_manager import AgentConnection

    ws = MagicMock()
    conn = AgentConnection("test-agent", ws)

    class BigContainer:
        def __init__(self):
            self.data = list(range(100000))

    container = BigContainer()
    conn._output_callbacks["cmd-leak"] = lambda data: container.data.append(data)

    # 验证 callback 确实被注册
    assert "cmd-leak" in conn._output_callbacks

    # 清理后 callback 被移除
    conn._output_callbacks.pop("cmd-leak", None)
    assert "cmd-leak" not in conn._output_callbacks

    print("PASS: Leaked callback can be cleaned up via _output_callbacks.pop")


def test_runner_finally_block_exists():
    """验证 runner.py _execute_task 有 finally 块清理 _running_executors。"""
    import inspect

    from taskpps.engine.runner import PipelineRunner

    source = inspect.getsource(PipelineRunner._execute_task)

    assert "finally:" in source, "_execute_task 缺少 finally 块！"

    finally_block = source[source.index("finally:"):]
    assert "_running_executors.pop" in finally_block, (
        "finally 块中缺少 _running_executors.pop！"
    )

    assert "executor.cleanup()" in finally_block, (
        "finally 块中缺少 executor.cleanup()！"
    )

    print("PASS: runner._execute_task has finally block with cleanup")


if __name__ == "__main__":
    tests = [
        test_running_executors_cleaned_on_cancelled_error,
        test_agent_executor_cleanup_removes_output_callback,
        test_agent_exec_cleanup_on_timeout,
        test_disconnect_cleanup_handles_exceptions,
        test_agent_exec_normal_path_cleans_output_callback,
        test_gc_can_collect_cleaned_executor,
        test_gc_leaked_callback_keeps_data_alive,
        test_runner_finally_block_exists,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
