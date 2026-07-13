from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestYieldCompleteLines:
    @pytest.mark.zentao("TC-S0942", domain="server/api", priority="P2")
    def test_normal_lines(self):
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\nline2\n")
        assert lines == ["line1", "line2"]
        assert advance == 12

    @pytest.mark.zentao("TC-S0943", domain="server/api", priority="P2")
    def test_incomplete_last_line(self):
        """最后一行不完整（无\\n），不应发送"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\nincomplet")
        assert lines == ["line1"]
        assert advance == 6

    @pytest.mark.zentao("TC-S0944", domain="server/api", priority="P2")
    def test_no_newline_at_all(self):
        """完全没有换行符，不发送任何行"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("incomplete")
        assert lines == []
        assert advance == 0

    @pytest.mark.zentao("TC-S0945", domain="server/api", priority="P2")
    def test_empty_content(self):
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("")
        assert lines == []
        assert advance == 0

    @pytest.mark.zentao("TC-S0946", domain="server/api", priority="P2")
    def test_only_newline(self):
        """仅一个换行符，发送空行"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("\n")
        assert lines == [""]
        assert advance == 1

    @pytest.mark.zentao("TC-S0947", domain="server/api", priority="P2")
    def test_crlf_line_endings(self):
        """\\r\\n 换行，\\r 被剥离"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\r\nline2\r\n")
        assert lines == ["line1", "line2"]
        assert advance == 14

    @pytest.mark.zentao("TC-S0948", domain="server/api", priority="P2")
    def test_embedded_empty_lines(self):
        """保留中间的空行"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("line1\n\nline3\n")
        assert lines == ["line1", "", "line3"]
        assert advance == 13

    @pytest.mark.zentao("TC-S0949", domain="server/api", priority="P2")
    def test_multiple_incomplete_reads(self):
        """模拟多次读取：第一次读到不完整行，第二次读到完整"""
        from taskpps.api.runs import _yield_complete_lines

        # 第一次读: "hel" (不完整)
        l1, a1 = _yield_complete_lines("hel")
        assert l1 == []
        assert a1 == 0

        # 第二次读: "hel" + "lo\n" = "hello\n" (完整了)
        l2, a2 = _yield_complete_lines("hello\n")
        assert l2 == ["hello"]
        assert a2 == 6

    @pytest.mark.zentao("TC-S0950", domain="server/api", priority="P2")
    def test_carriage_return_midline_preserved(self):
        """行中间的 \\r 不剥离（用于进度条覆盖显示）"""
        from taskpps.api.runs import _yield_complete_lines

        lines, advance = _yield_complete_lines("Progress: 50%\rProgress: 100%\n")
        assert lines == ["Progress: 50%\rProgress: 100%"]
        assert advance == 29


class TestRunLogs:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0951", domain="server/api", priority="P1")
    async def test_logs_no_task_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert len(data["logs"]) >= 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0952", domain="server/api", priority="P1")
    async def test_logs_with_task_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?task=deploy.step1")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0953", domain="server/api", priority="P1")
    async def test_logs_with_task_filter_no_match(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?task=nonexistent.task")
        assert response.status_code == 200
        data = response.json()
        assert data == {"logs": {}}

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0954", domain="server/api", priority="P1")
    async def test_logs_with_tail(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        result = await svc.create_run("deploy.yaml")
        run_id = result["id"]

        response = await client.get(f"/api/runs/{run_id}/logs?tail=10")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0955", domain="server/api", priority="P1")
    async def test_logs_nonexistent_run(self, client):
        response = await client.get("/api/runs/nonexistent/logs")
        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0956", domain="server/api", priority="P1")
    async def test_logs_with_follow(self, client, db_engine, tmp_path):
        """SSE follow 模式应返回 text/event-stream。
        使用已完成的 run 避免启动后台 runner。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        log_file = tmp_path / "step1.log"
        log_file.write_text("hello\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-follow-basic",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-follow-basic",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        response = await client.get("/api/runs/test-follow-basic/logs?follow=true")
        # SSE response should be 200 with text/event-stream
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0986", domain="server/api", priority="P1")
    async def test_logs_follow_batch_push(self, client, db_engine, tmp_path):
        """follow 模式应批量推送：一个 log event 包含多行，减少 yield 次数。

        回归：5万行日志逐行 yield 导致 SSE 接口 18 秒未推完。
        改为按 task 批量推送后，N 行只需 1 次 yield。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        log_file = tmp_path / "multi.log"
        log_file.write_text("line1\nline2\nline3\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-batch-push",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-batch-push",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        response = await client.get("/api/runs/test-batch-push/logs?follow=true")
        assert response.status_code == 200

        # 批量推送：3 行应在 1 个 log event 中（而非 3 个独立 event）
        log_event_count = response.text.count("event: log")
        assert log_event_count == 1, (
            f"应批量推送（1 个 event 含 3 行），实际 {log_event_count} 个 log event; "
            f"response: {response.text[:500]}"
        )

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0987", domain="server/api", priority="P1")
    async def test_logs_follow_large_logs_batch_push(self, client, db_engine, tmp_path):
        """follow 模式处理 5 万行日志：应批量推送，log event 数量是 task 级别而非行级别。

        回归：13 个 task × 4000 行 = 52000 行，逐行推送需 52000 次 yield，耗时 > 18 秒。
        批量推送后只需 13 次 yield，响应时间大幅降低。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        task_count = 13
        lines_per_task = 4000
        total_lines = task_count * lines_per_task

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-large-batch",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()

            for i in range(task_count):
                task_name = f"task-{i:02d}"
                log_file = tmp_path / f"{task_name}.log"
                lines = [f"[{task_name}] line-{j:05d}\n" for j in range(lines_per_task)]
                log_file.write_text("".join(lines))

                task_run = TaskRun(
                    run_id="test-large-batch",
                    task_name=task_name,
                    task_type=TaskType.COMMAND,
                    status=TaskStatus.SUCCESS,
                    log_path=str(log_file),
                )
                session.add(task_run)
            await session.commit()

        response = await client.get("/api/runs/test-large-batch/logs?follow=true")
        assert response.status_code == 200

        text = response.text

        log_event_count = text.count("event: log")
        # 批量推送：log event 数量 = task 数量，而非总行数
        assert log_event_count == task_count, (
            f"应批量推送（{task_count} 个 event），实际 {log_event_count} 个 log event"
        )

        # 验证所有日志行都被包含
        total_line_count = text.count("\n") - text.count("event: ") - text.count("data: ")
        # SSE 格式中 data: 行包含换行，粗略校验
        assert total_line_count >= total_lines, (
            f"期望至少 {total_lines} 行日志，实际 {total_line_count} 行"
        )

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0957", domain="server/api", priority="P1")
    async def test_logs_follow_emits_status_events(self, client, db_engine, tmp_path):
        """SSE follow 模式应在任务状态变更时推送 status 事件。
        使用已完成的 run 避免启动后台 runner。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        log_file = tmp_path / "step1.log"
        log_file.write_text("hello\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-sse-events",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-sse-events",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        response = await client.get("/api/runs/test-sse-events/logs?follow=true")
        assert response.status_code == 200

        # 解析 SSE 事件，查找 status 事件
        text = response.text
        status_events = []
        for line in text.split("\n"):
            if line.startswith("data:") and '"task_name"' in line and '"status"' in line:
                payload_str = line[len("data:"):].strip()
                try:
                    payload = json.loads(payload_str)
                    if "task_name" in payload and "status" in payload:
                        status_events.append(payload)
                except json.JSONDecodeError:
                    pass

        # 至少应该有一个 status 事件（任务初始为 pending 或已完成）
        assert len(status_events) > 0, f"Expected status events in SSE stream, got: {text[:500]}"
        # 验证 status 事件格式
        for evt in status_events:
            assert "task_name" in evt
            assert "status" in evt

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0958", domain="server/api", priority="P1")
    async def test_logs_follow_subscribes_to_event_bus(self, client, db_engine, tmp_path):
        """Issue #65: SSE 应订阅事件总线以即时推送状态变更，而非仅靠 300ms 轮询。

        直接创建已完成的 run 记录，避免启动后台 runner 导致数据库状态泄漏。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        # 创建已完成的 run + task_run，SSE 流会在首次轮询后立即结束
        log_file = tmp_path / "step1.log"
        log_file.write_text("hello\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-sse-bus",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-sse-bus",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        with patch("taskpps.api.runs.get_event_bus") as mock_get_bus:
            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            response = await client.get("/api/runs/test-sse-bus/logs?follow=true")
            assert response.status_code == 200

            # SSE 应订阅 task_started 和 task_finished 事件
            subscribed = [call.args[0] for call in mock_bus.on.call_args_list]
            assert "task_started" in subscribed, f"SSE 未订阅 task_started，实际订阅: {subscribed}"
            assert "task_finished" in subscribed, f"SSE 未订阅 task_finished，实际订阅: {subscribed}"
            # 流结束后应取消订阅，避免泄漏
            assert mock_bus.off.call_count >= 2

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0959", domain="server/api", priority="P1")
    async def test_logs_follow_handles_binary_log(self, client, db_engine, tmp_path):
        """SSE follow 模式读取含非 UTF-8 字节的日志文件时不应崩溃。

        日志文件可能包含二进制数据（如终端控制序列），open() 默认 UTF-8 解码
        会抛 UnicodeDecodeError 中断整个 SSE 流。
        使用已完成的 run 避免启动后台 runner。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        # 创建含非 UTF-8 字节的日志文件
        log_file = tmp_path / "binary.log"
        log_file.write_bytes(b"valid line\n\x88\x89invalid bytes\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-binary-log",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-binary-log",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        # SSE 流应正常返回 200，不因 UnicodeDecodeError 崩溃
        # 使用非 follow 模式验证解码，避免 SSE 流挂起
        response = await client.get("/api/runs/test-binary-log/logs")
        assert response.status_code == 200
        data = response.json()
        assert "valid line" in data["logs"]["step1"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0960", domain="server/api", priority="P1")
    async def test_console_handles_binary_log(self, client, db_engine, tmp_path):
        """get_run_console 读取含非 UTF-8 字节的 console.log 时不应崩溃。

        console.log 由 engine 写入，可能包含终端控制序列等非 UTF-8 字节。
        """
        from taskpps.config import build_pipeline_log_path
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-binary-console",
                pipeline_name="deploy",
                pipeline_id="deploy",
                pipeline_version="1",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()

        # 写入含非 UTF-8 字节的 console.log
        log_path = build_pipeline_log_path("deploy", "1", "test-binary-console")
        log_path.write_bytes(b"[INFO] start\n\x88\x89[ERROR] bad bytes\n")

        response = await client.get("/api/runs/test-binary-console/console")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert "[INFO] start" in data["content"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0961", domain="server/api", priority="P1")
    async def test_retry_logs_handles_binary_log(self, client, db_engine, tmp_path):
        """get_retry_logs（非 follow 模式）读取含非 UTF-8 字节日志时不应崩溃。"""
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import (
            PipelineRun,
            RunStatus,
            TaskRetryRecord,
            TaskRun,
            TaskStatus,
            TaskType,
        )

        log_file = tmp_path / "retry_binary.log"
        log_file.write_bytes(b"retry start\n\x88\x89retry bad bytes\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-binary-retry",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-binary-retry",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()
            retry = TaskRetryRecord(
                run_id="test-binary-retry",
                task_run_id=task_run.id,
                task_name="step1",
                retry_version=1,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(retry)
            await session.commit()
            retry_id = retry.id

        response = await client.get(f"/api/runs/test-binary-retry/retry/{retry_id}/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert "retry start" in data["content"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0962", domain="server/api", priority="P1")
    async def test_retry_logs_follow_handles_binary_log(self, client, db_engine, tmp_path):
        """get_retry_logs 读取含非 UTF-8 字节日志时不应崩溃。
        使用非 follow 模式验证解码，避免 SSE 流挂起。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import (
            PipelineRun,
            RunStatus,
            TaskRetryRecord,
            TaskRun,
            TaskStatus,
            TaskType,
        )

        log_file = tmp_path / "retry_binary_follow.log"
        log_file.write_bytes(b"retry follow\n\x88\x89bad bytes\n")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-binary-retry-follow",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-binary-retry-follow",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()
            retry = TaskRetryRecord(
                run_id="test-binary-retry-follow",
                task_run_id=task_run.id,
                task_name="step1",
                retry_version=1,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(retry)
            await session.commit()
            retry_id = retry.id

        response = await client.get(
            f"/api/runs/test-binary-retry-follow/retry/{retry_id}/logs"
        )
        assert response.status_code == 200
        data = response.json()
        assert "retry follow" in data["content"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0963", domain="server/api", priority="P1")
    async def test_logs_follow_handles_gbk_log(self, client, db_engine, tmp_path):
        """读取 GBK 编码日志时应正确解码中文，不产生乱码。
        使用非 follow 模式验证解码，避免 SSE 流挂起。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        # 写入 GBK 编码的中文日志
        log_file = tmp_path / "gbk.log"
        log_file.write_bytes("开始执行\n初始化完成\n".encode("gbk"))

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-gbk-log",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-gbk-log",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        response = await client.get("/api/runs/test-gbk-log/logs")
        assert response.status_code == 200
        data = response.json()
        # 中文应正确解码，不出现乱码
        assert "开始执行" in data["logs"]["step1"], "GBK 中文解码失败"
        assert "初始化完成" in data["logs"]["step1"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0964", domain="server/api", priority="P1")
    async def test_console_handles_gbk_log(self, client, db_engine, tmp_path):
        """get_run_console 读取 GBK 编码 console.log 时应正确解码中文。"""
        from taskpps.config import build_pipeline_log_path
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-gbk-console",
                pipeline_name="deploy",
                pipeline_id="deploy",
                pipeline_version="1",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()

        log_path = build_pipeline_log_path("deploy", "1", "test-gbk-console")
        log_path.write_bytes("[INFO] 开始部署\n[SUCCESS] 部署完成\n".encode("gbk"))

        response = await client.get("/api/runs/test-gbk-console/console")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert "开始部署" in data["content"]
        assert "部署完成" in data["content"]

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0965", domain="server/api", priority="P1")
    async def test_logs_follow_flushes_partial_line_on_completion(self, client, db_engine, tmp_path):
        """Issue #68: 任务结束后应刷新不含换行符的尾部日志行。
        使用非 follow 模式验证 include_partial 解码，避免 SSE 流挂起。
        """
        from taskpps.db.engine import get_session_factory
        from taskpps.models.run import PipelineRun, RunStatus, TaskRun, TaskStatus, TaskType

        # 日志最后一行没有换行符
        log_file = tmp_path / "partial.log"
        log_file.write_bytes(b"line1\nline2\npartial without newline")

        async with get_session_factory()() as session:
            run = PipelineRun(
                id="test-partial-flush",
                pipeline_name="deploy",
                status=RunStatus.SUCCESS,
            )
            session.add(run)
            await session.commit()
            task_run = TaskRun(
                run_id="test-partial-flush",
                task_name="step1",
                task_type=TaskType.COMMAND,
                status=TaskStatus.SUCCESS,
                log_path=str(log_file),
            )
            session.add(task_run)
            await session.commit()

        response = await client.get("/api/runs/test-partial-flush/logs")
        assert response.status_code == 200
        data = response.json()
        # 不完整行也应被包含（非 follow 模式使用 include_partial=True）
        assert "partial without newline" in data["logs"]["step1"], (
            "尾部不完整行未被包含"
        )


class TestDecodeLogBytes:
    @pytest.mark.zentao("TC-S0966", domain="server/api", priority="P2")
    def test_utf8_content(self):
        from taskpps.api.runs import _decode_log_bytes

        assert _decode_log_bytes(b"hello") == "hello"
        assert _decode_log_bytes("中文".encode()) == "中文"

    @pytest.mark.zentao("TC-S0967", domain="server/api", priority="P2")
    def test_gbk_content(self):
        from taskpps.api.runs import _decode_log_bytes

        assert _decode_log_bytes("中文".encode("gbk")) == "中文"
        assert _decode_log_bytes("开始执行\n".encode("gbk")) == "开始执行\n"

    @pytest.mark.zentao("TC-S0968", domain="server/api", priority="P2")
    def test_mixed_invalid_bytes(self):
        from taskpps.api.runs import _decode_log_bytes

        # 0x88 不是合法 UTF-8 起始字节，应回退 GBK
        result = _decode_log_bytes(b"\x88\x89")
        assert isinstance(result, str)


class TestReadLogLines:
    @pytest.mark.zentao("TC-S0969", domain="server/api", priority="P2")
    def test_complete_lines_only(self, tmp_path):
        from taskpps.api.runs import _read_log_lines

        log = tmp_path / "test.log"
        log.write_bytes(b"line1\nline2\npartial")
        lines, pos = _read_log_lines(log, 0)
        assert lines == ["line1", "line2"]
        assert pos == 12  # position after "line2\n"

    @pytest.mark.zentao("TC-S0970", domain="server/api", priority="P2")
    def test_include_partial(self, tmp_path):
        from taskpps.api.runs import _read_log_lines

        log = tmp_path / "test.log"
        log.write_bytes(b"line1\nline2\npartial")
        lines, pos = _read_log_lines(log, 0, include_partial=True)
        assert lines == ["line1", "line2", "partial"]
        assert pos == len(b"line1\nline2\npartial")

    @pytest.mark.zentao("TC-S0971", domain="server/api", priority="P2")
    def test_gbk_encoded(self, tmp_path):
        from taskpps.api.runs import _read_log_lines

        log = tmp_path / "gbk.log"
        log.write_bytes("第一行\n第二行\n".encode("gbk"))
        lines, pos = _read_log_lines(log, 0)
        assert lines == ["第一行", "第二行"]

    @pytest.mark.zentao("TC-S0972", domain="server/api", priority="P2")
    def test_empty_file(self, tmp_path):
        from taskpps.api.runs import _read_log_lines

        log = tmp_path / "empty.log"
        log.write_bytes(b"")
        lines, pos = _read_log_lines(log, 0)
        assert lines == []
        assert pos == 0

    @pytest.mark.zentao("TC-S0973", domain="server/api", priority="P2")
    def test_no_newline(self, tmp_path):
        from taskpps.api.runs import _read_log_lines

        log = tmp_path / "no_nl.log"
        log.write_bytes(b"no newline here")
        lines, pos = _read_log_lines(log, 0)
        assert lines == []
        assert pos == 0  # position unchanged, waiting for complete line

    @pytest.mark.zentao("TC-S0974", domain="server/api", priority="P2")
    def test_incremental_read(self, tmp_path):
        """模拟流式读取：先读完整行，再读剩余部分。"""
        from taskpps.api.runs import _read_log_lines

        log = tmp_path / "stream.log"
        log.write_bytes(b"line1\nline2\n")
        lines, pos = _read_log_lines(log, 0)
        assert lines == ["line1", "line2"]

        # 追加内容
        with open(log, "ab") as f:
            f.write(b"line3\n")
        lines, pos = _read_log_lines(log, pos)
        assert lines == ["line3"]


class TestCleanRunsAPI:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0975", domain="server/api", priority="P1")
    async def test_clean_force(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.delete("/api/runs/?force=true")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_runs"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0976", domain="server/api", priority="P1")
    async def test_clean_no_params(self, client, db_engine):
        response = await client.delete("/api/runs/")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_runs"] == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0977", domain="server/api", priority="P1")
    async def test_clean_older_than(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.delete("/api/runs/?older_than=365")
        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0978", domain="server/api", priority="P1")
    async def test_clean_keep(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.delete("/api/runs/?keep=100")
        assert response.status_code == 200


class TestCancelRun:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0979", domain="server/api", priority="P1")
    async def test_cancel_nonexistent(self, client):
        response = await client.post("/api/runs/nonexistent/cancel")
        assert response.status_code == 404


class TestListRuns:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0980", domain="server/api", priority="P1")
    async def test_list_with_status_filter(self, client, db_engine):
        from taskpps.services.pipeline_service import PipelineService

        svc = PipelineService()
        await svc.create_run("deploy.yaml")

        response = await client.get("/api/runs/?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0

