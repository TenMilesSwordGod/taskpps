from __future__ import annotations

import asyncio

import pytest


async def _wait_run_done(client, run_id, timeout=6):
    for _ in range(int(timeout / 0.2)):
        await asyncio.sleep(0.2)
        resp = await client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in ("success", "failed", "cancelled", "partial"):
            return status
    pytest.fail(f"Pipeline did not complete in time, last status={status}")
    return status


@pytest.mark.asyncio
class TestRetryFunctional:
    @pytest.mark.zentao("TC-S0041", domain="server/functional", priority="P0")
    async def test_retry_full_flow(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        assert resp.status_code in (200, 201)
        run_id = resp.json()["id"]

        status = await _wait_run_done(client, run_id)
        assert status == "success"

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )
        assert retry_resp.status_code == 200
        data = retry_resp.json()
        assert len(data["retry_records"]) == 1
        assert data["retry_records"][0]["task_name"] == "deploy.step1"
        assert data["retry_records"][0]["status"] == "success"

        versions_resp = await client.get(f"/api/runs/{run_id}/retry/versions")
        assert versions_resp.status_code == 200
        v = versions_resp.json()
        assert "deploy.step1" in v["task_retries"]
        assert len(v["task_retries"]["deploy.step1"]) == 1

    @pytest.mark.zentao("TC-S0042", domain="server/functional", priority="P1")
    async def test_retry_with_dependencies(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step2"], "include_upstream": True},
        )
        assert retry_resp.status_code == 200
        data = retry_resp.json()
        assert len(data["retry_records"]) == 2
        task_names = {r["task_name"] for r in data["retry_records"]}
        assert task_names == {"deploy.step1", "deploy.step2"}

    @pytest.mark.zentao("TC-S0043", domain="server/functional", priority="P1")
    async def test_retry_whole_subpipeline(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"subpipeline": "deploy"},
        )
        assert retry_resp.status_code == 200
        data = retry_resp.json()
        assert len(data["retry_records"]) == 2
        task_names = {r["task_name"] for r in data["retry_records"]}
        assert task_names == {"deploy.step1", "deploy.step2"}

    @pytest.mark.zentao("TC-S0044", domain="server/functional", priority="P1")
    async def test_retry_after_failure_fixes_task(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "fail_test.yaml", "params": {}})
        run_id = resp.json()["id"]
        status = await _wait_run_done(client, run_id)
        assert status == "failed"

        get_resp = await client.get(f"/api/runs/{run_id}")
        tasks = get_resp.json()["tasks"]
        failed_task = next(t for t in tasks if t["task_name"] == "fail_test.will-fail")
        assert failed_task["status"] == "failed"

        skipped_task = next(t for t in tasks if t["task_name"] == "fail_test.after-fail")
        assert skipped_task["status"] == "skipped"

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={
                "tasks": ["fail_test.will-fail"],
                "command_overrides": {"fail_test.will-fail": "echo fixed"},
            },
        )
        assert retry_resp.status_code == 200
        data = retry_resp.json()
        assert data["retry_records"][0]["status"] == "success"

        get_resp2 = await client.get(f"/api/runs/{run_id}")
        updated_task = next(t for t in get_resp2.json()["tasks"] if t["task_name"] == "fail_test.will-fail")
        assert updated_task["status"] == "success"

    @pytest.mark.zentao("TC-S0045", domain="server/functional", priority="P1")
    async def test_retry_continue_pipeline(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "continue_test.yaml", "params": {}})
        run_id = resp.json()["id"]
        status = await _wait_run_done(client, run_id)
        assert status in ("failed", "partial")

        get_resp = await client.get(f"/api/runs/{run_id}")
        tasks = get_resp.json()["tasks"]
        failed_task = next(t for t in tasks if t["task_name"] == "continue_test.will-fail")
        assert failed_task["status"] == "failed"

        independent_task = next(t for t in tasks if t["task_name"] == "continue_test.independent")
        assert independent_task["status"] == "success"

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={
                "tasks": ["continue_test.will-fail"],
                "command_overrides": {"continue_test.will-fail": "echo ok"},
            },
        )
        assert retry_resp.status_code == 200
        assert retry_resp.json()["retry_records"][0]["status"] == "success"

    @pytest.mark.zentao("TC-S0046", domain="server/functional", priority="P2")
    async def test_multiple_retries_increment_version(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )

        await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )

        versions_resp = await client.get(f"/api/runs/{run_id}/retry/versions")
        assert versions_resp.status_code == 200
        v = versions_resp.json()
        assert len(v["task_retries"]["deploy.step1"]) == 2
        versions = [r["retry_version"] for r in v["task_retries"]["deploy.step1"]]
        assert versions == [1, 2]
        assert v["selected"]["deploy.step1"] is not None

    @pytest.mark.zentao("TC-S0047", domain="server/functional", priority="P1")
    async def test_retry_on_nonexistent_run(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post(
            "/api/runs/nonexistent/retry",
            json={"tasks": ["deploy.step1"]},
        )
        assert resp.status_code == 400

    @pytest.mark.zentao("TC-S0048", domain="server/functional", priority="P1")
    async def test_retry_nonexistent_task(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.nonexistent"]},
        )
        assert resp.status_code == 400

    @pytest.mark.zentao("TC-S0049", domain="server/functional", priority="P1")
    async def test_retry_both_tasks_and_subpipeline_rejected(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"], "subpipeline": "deploy"},
        )
        assert resp.status_code == 400

    @pytest.mark.zentao("TC-S0050", domain="server/functional", priority="P1")
    async def test_retry_missing_both_tasks_and_subpipeline(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={},
        )
        assert resp.status_code == 400

    @pytest.mark.zentao("TC-S0051", domain="server/functional", priority="P2")
    async def test_dependency_tree_api(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.get(f"/api/runs/{run_id}/retry/dependency-tree?task=deploy.step2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target"] == "deploy.step2"
        tree = data["tree"]
        assert len(tree) == 2
        names = [n["name"] for n in tree]
        assert "deploy.step1" in names
        assert "deploy.step2" in names

        step1_node = next(n for n in tree if n["name"] == "deploy.step1")
        assert step1_node["upstream_of_target"] is True
        assert step1_node["mandatory_if_upstream"] is True

        step2_node = next(n for n in tree if n["name"] == "deploy.step2")
        assert step2_node["upstream_of_target"] is False

    @pytest.mark.zentao("TC-S0052", domain="server/functional", priority="P2")
    async def test_dependency_tree_upstream_of_first_task(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.get(f"/api/runs/{run_id}/retry/dependency-tree?task=deploy.step1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target"] == "deploy.step1"
        tree = data["tree"]
        assert len(tree) == 1
        assert tree[0]["name"] == "deploy.step1"
        assert tree[0]["upstream_of_target"] is False

    @pytest.mark.zentao("TC-S0053", domain="server/functional", priority="P1")
    async def test_retry_command_edit_flow(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )
        retry_id = retry_resp.json()["retry_records"][0]["id"]

        cmd_resp = await client.get(f"/api/runs/{run_id}/retry/{retry_id}/command")
        assert cmd_resp.status_code == 200
        cmd_data = cmd_resp.json()
        assert cmd_data["retry_id"] == retry_id
        assert cmd_data["editable"] is False
        assert cmd_data["status"] == "success"

        edit_resp = await client.put(
            f"/api/runs/{run_id}/retry/{retry_id}/command",
            json={"command": "echo new_command"},
        )
        assert edit_resp.status_code == 400

    @pytest.mark.zentao("TC-S0054", domain="server/functional", priority="P1")
    async def test_retry_command_edit_pending(self, client, setup_project, tmp_project, db_engine, clean_db):
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository
        from taskpps.models.run import TaskStatus

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="deploy.yaml")
            task_repo = TaskRunRepository(session)
            tr = await task_repo.create_task_run(
                run_id=run.id, task_name="deploy.step1", task_type="command",
                subpipeline_name="deploy",
            )
            retry_repo = RetryRecordRepository(session)
            record = await retry_repo.create_retry_record(
                run_id=run.id, task_run_id=tr.id,
                task_name="deploy.step1", subpipeline_name="deploy",
                retry_version=1, command="echo original",
                original_command="echo original", log_path="/tmp/test.log",
            )
            retry_id = record.id
            run_id = run.id

        cmd_resp = await client.get(f"/api/runs/{run_id}/retry/{retry_id}/command")
        assert cmd_resp.status_code == 200
        cmd_data = cmd_resp.json()
        assert cmd_data["editable"] is True
        assert cmd_data["status"] == "pending"

        edit_resp = await client.put(
            f"/api/runs/{run_id}/retry/{retry_id}/command",
            json={"command": "echo edited"},
        )
        assert edit_resp.status_code == 200
        assert edit_resp.json()["command"] == "echo edited"

        cmd_resp2 = await client.get(f"/api/runs/{run_id}/retry/{retry_id}/command")
        assert cmd_resp2.json()["resolved_command"] == "echo edited"

    @pytest.mark.zentao("TC-S0055", domain="server/functional", priority="P1")
    async def test_select_retry_report(self, client, setup_project, tmp_project, db_engine, clean_db):
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository
        from taskpps.models.run import TaskStatus

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="deploy.yaml")
            task_repo = TaskRunRepository(session)
            tr = await task_repo.create_task_run(
                run_id=run.id, task_name="deploy.step1", task_type="command",
                subpipeline_name="deploy",
            )
            tr.status = TaskStatus.FAILED
            session.add(tr)
            await session.commit()

            retry_repo = RetryRecordRepository(session)
            r1 = await retry_repo.create_retry_record(
                run_id=run.id, task_run_id=tr.id,
                task_name="deploy.step1", subpipeline_name="deploy",
                retry_version=1, command="echo v1",
                original_command="echo v1", log_path="/tmp/v1.log",
            )
            await retry_repo.update_retry_status(r1.id, TaskStatus.SUCCESS, exit_code=0)

            r2 = await retry_repo.create_retry_record(
                run_id=run.id, task_run_id=tr.id,
                task_name="deploy.step1", subpipeline_name="deploy",
                retry_version=2, command="echo v2",
                original_command="echo v2", log_path="/tmp/v2.log",
            )
            await retry_repo.update_retry_status(r2.id, TaskStatus.SUCCESS, exit_code=0)

            run_id = run.id

        versions_resp = await client.get(f"/api/runs/{run_id}/retry/versions")
        assert versions_resp.status_code == 200
        v = versions_resp.json()
        assert len(v["task_retries"]["deploy.step1"]) == 2
        assert v["selected"]["deploy.step1"] is None

        select_resp = await client.post(
            f"/api/runs/{run_id}/retry/{r1.id}/select-report",
            json={"task_name": "deploy.step1", "selected_retry_id": r1.id},
        )
        assert select_resp.status_code == 200

        versions_resp2 = await client.get(f"/api/runs/{run_id}/retry/versions")
        v2 = versions_resp2.json()
        assert v2["selected"]["deploy.step1"] == r1.id

    @pytest.mark.zentao("TC-S0056", domain="server/functional", priority="P1")
    async def test_batch_select_retry_report(self, client, setup_project, tmp_project, db_engine, clean_db):
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository
        from taskpps.models.run import TaskStatus

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="deploy.yaml")
            task_repo = TaskRunRepository(session)
            tr1 = await task_repo.create_task_run(
                run_id=run.id, task_name="deploy.step1", task_type="command",
                subpipeline_name="deploy",
            )
            tr1.status = TaskStatus.FAILED
            tr2 = await task_repo.create_task_run(
                run_id=run.id, task_name="deploy.step2", task_type="command",
                subpipeline_name="deploy",
            )
            tr2.status = TaskStatus.FAILED
            session.add(tr1)
            session.add(tr2)
            await session.commit()

            retry_repo = RetryRecordRepository(session)
            r1 = await retry_repo.create_retry_record(
                run_id=run.id, task_run_id=tr1.id,
                task_name="deploy.step1", subpipeline_name="deploy",
                retry_version=1, command="echo v1",
                original_command="echo v1", log_path="/tmp/v1.log",
            )
            await retry_repo.update_retry_status(r1.id, TaskStatus.SUCCESS, exit_code=0)

            r2 = await retry_repo.create_retry_record(
                run_id=run.id, task_run_id=tr2.id,
                task_name="deploy.step2", subpipeline_name="deploy",
                retry_version=1, command="echo v2",
                original_command="echo v2", log_path="/tmp/v2.log",
            )
            await retry_repo.update_retry_status(r2.id, TaskStatus.SUCCESS, exit_code=0)

            run_id = run.id
            r1_id = r1.id
            r2_id = r2.id

        batch_resp = await client.post(
            f"/api/runs/{run_id}/retry/select-report",
            json={"selections": {"deploy.step1": r1_id, "deploy.step2": r2_id}},
        )
        assert batch_resp.status_code == 200

        versions_resp = await client.get(f"/api/runs/{run_id}/retry/versions")
        v = versions_resp.json()
        assert v["selected"]["deploy.step1"] == r1_id
        assert v["selected"]["deploy.step2"] == r2_id

    @pytest.mark.zentao("TC-S0057", domain="server/functional", priority="P1")
    async def test_retry_get_record(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )
        retry_id = retry_resp.json()["retry_records"][0]["id"]

        get_resp = await client.get(f"/api/runs/{run_id}/retry/{retry_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == retry_id
        assert data["task_name"] == "deploy.step1"
        assert data["status"] == "success"

    @pytest.mark.zentao("TC-S0058", domain="server/functional", priority="P1")
    async def test_retry_get_nonexistent_record(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        get_resp = await client.get(f"/api/runs/{run_id}/retry/nonexistent-id")
        assert get_resp.status_code == 404

    @pytest.mark.zentao("TC-S0059", domain="server/functional", priority="P1")
    async def test_retry_log_api(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )
        retry_id = retry_resp.json()["retry_records"][0]["id"]

        log_resp = await client.get(f"/api/runs/{run_id}/retry/{retry_id}/logs")
        assert log_resp.status_code == 200
        log_data = log_resp.json()
        assert log_data["exists"] is True
        assert "hello" in log_data["content"]

    @pytest.mark.zentao("TC-S0060", domain="server/functional", priority="P1")
    async def test_retry_log_with_tail(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "deploy.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        retry_resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.step1"]},
        )
        retry_id = retry_resp.json()["retry_records"][0]["id"]

        log_resp = await client.get(f"/api/runs/{run_id}/retry/{retry_id}/logs?tail=1")
        assert log_resp.status_code == 200
        assert log_resp.json()["exists"] is True

    @pytest.mark.zentao("TC-S0061", domain="server/functional", priority="P1")
    async def test_retry_task_not_found_updates_record_to_failed(self, db_engine, clean_db):
        from taskpps.domain.context import ExecutionContext
        from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask, ResolvedSubPipeline
        from taskpps.engine.retry_runner import RetryRunner
        from taskpps.models.run import TaskStatus
        from taskpps.schemas.pipeline import PipelineConfig
        from unittest.mock import AsyncMock, patch

        mock_task = ResolvedTask(name="step1", task_type="command", command="echo hello")
        mock_sub = ResolvedSubPipeline(name="deploy", tasks=[mock_task], config=PipelineConfig())
        pipeline = ResolvedPipeline(name="deploy", subpipelines=[mock_sub], top_config=PipelineConfig())
        ctx = ExecutionContext(pipeline=pipeline, run_id="test_run")

        runner = RetryRunner(run_id="r1", pipeline=pipeline, context=ctx)
        runner._update_record = AsyncMock()

        task_plan = [{
            "name": "deploy.nonexistent",
            "command": "echo x",
            "retry_record_id": "rec_1",
            "log_path": "/tmp/x_notfound.log",
        }]

        with patch("taskpps.engine.retry_runner.get_event_bus"):
            results = await runner.retry_tasks(task_plan)

        assert not results["deploy.nonexistent"].success
        assert "not found" in results["deploy.nonexistent"].stderr
        runner._update_record.assert_called_once()
        call_args = runner._update_record.call_args
        assert call_args[0][1] == TaskStatus.FAILED

    @pytest.mark.zentao("TC-S0062", domain="server/functional", priority="P1")
    async def test_failed_retry_does_not_overwrite_successful_selection(self, client, setup_project, tmp_project, db_engine, clean_db):
        from taskpps.db.engine import get_session_factory
        from taskpps.db.repository import RetryRecordRepository, RunRepository, TaskRunRepository
        from taskpps.models.run import TaskStatus

        async with get_session_factory()() as session:
            run_repo = RunRepository(session)
            run = await run_repo.create_run(pipeline_name="test", pipeline_file="deploy.yaml")
            task_repo = TaskRunRepository(session)
            tr = await task_repo.create_task_run(
                run_id=run.id, task_name="deploy.step1", task_type="command",
                subpipeline_name="deploy",
            )
            tr.status = TaskStatus.FAILED
            tr.selected_retry_id = "old_id"
            session.add(tr)
            await session.commit()

            retry_repo = RetryRecordRepository(session)
            r1 = await retry_repo.create_retry_record(
                run_id=run.id, task_run_id=tr.id,
                task_name="deploy.step1", subpipeline_name="deploy",
                retry_version=1, command="echo v1",
                original_command="echo v1", log_path="/tmp/v1_sel.log",
            )
            await retry_repo.update_retry_status(r1.id, TaskStatus.FAILED, exit_code=1)

            run_id = run.id
            r1_id = r1.id

        from taskpps.services.pipeline_service import PipelineService
        svc = PipelineService()
        async with get_session_factory()() as session:
            await svc._auto_select_latest_retry(session, run_id, "deploy.step1")

        async with get_session_factory()() as session:
            task_repo = TaskRunRepository(session)
            updated = await task_repo.get_task_run(tr.id)
            assert updated.selected_retry_id == "old_id"


@pytest.mark.asyncio
class TestRetryDAGScenarios:
    @pytest.mark.zentao("TC-S0063", domain="server/functional", priority="P1")
    async def test_diamond_retry_middle_task(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        status = await _wait_run_done(client, run_id)
        assert status == "success"

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["diamond.b"], "include_upstream": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = {r["task_name"] for r in data["retry_records"]}
        assert names == {"diamond.a", "diamond.b"}

    @pytest.mark.zentao("TC-S0064", domain="server/functional", priority="P1")
    async def test_diamond_retry_last_task_includes_all_upstream(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["diamond.d"], "include_upstream": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = {r["task_name"] for r in data["retry_records"]}
        assert names == {"diamond.a", "diamond.b", "diamond.c", "diamond.d"}

    @pytest.mark.zentao("TC-S0065", domain="server/functional", priority="P1")
    async def test_diamond_retry_all_tasks(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"subpipeline": "diamond"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["retry_records"]) == 4

    @pytest.mark.zentao("TC-S0066", domain="server/functional", priority="P2")
    async def test_diamond_dependency_tree(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.get(f"/api/runs/{run_id}/retry/dependency-tree?task=diamond.d")
        assert resp.status_code == 200
        data = resp.json()
        tree = data["tree"]
        assert len(tree) == 4
        names = {n["name"] for n in tree}
        assert names == {"diamond.a", "diamond.b", "diamond.c", "diamond.d"}

        d_node = next(n for n in tree if n["name"] == "diamond.d")
        assert d_node["upstream_of_target"] is False
        assert d_node["mandatory_if_upstream"] is False

        b_node = next(n for n in tree if n["name"] == "diamond.b")
        assert b_node["upstream_of_target"] is True
        assert b_node["mandatory_if_upstream"] is True

    @pytest.mark.zentao("TC-S0067", domain="server/functional", priority="P1")
    async def test_diamond_retry_command_override(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={
                "tasks": ["diamond.b"],
                "command_overrides": {"diamond.b": "echo b_fixed"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["retry_records"][0]["command"] == "echo b_fixed"

    @pytest.mark.zentao("TC-S0068", domain="server/functional", priority="P1")
    async def test_continue_diamond_partial_failure(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "continue_diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        status = await _wait_run_done(client, run_id)
        assert status in ("failed", "partial")

        get_resp = await client.get(f"/api/runs/{run_id}")
        tasks = get_resp.json()["tasks"]

        a_task = next(t for t in tasks if t["task_name"] == "continue_diamond.a")
        assert a_task["status"] == "success"

        b_task = next(t for t in tasks if t["task_name"] == "continue_diamond.b")
        assert b_task["status"] == "failed"

        c_task = next(t for t in tasks if t["task_name"] == "continue_diamond.c")
        assert c_task["status"] == "success"

    @pytest.mark.zentao("TC-S0069", domain="server/functional", priority="P1")
    async def test_continue_diamond_retry_failed_branch(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "continue_diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={
                "tasks": ["continue_diamond.b"],
                "command_overrides": {"continue_diamond.b": "echo b_fixed"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["retry_records"][0]["status"] == "success"

    @pytest.mark.zentao("TC-S0070", domain="server/functional", priority="P1")
    async def test_multi_subpipeline_retry(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "multi_sub.yaml", "params": {}})
        run_id = resp.json()["id"]
        status = await _wait_run_done(client, run_id)
        assert status == "success"

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["deploy.upload"], "include_upstream": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = {r["task_name"] for r in data["retry_records"]}
        assert "build.compile" in names
        assert "build.test" in names
        assert "deploy.upload" in names

    @pytest.mark.zentao("TC-S0071", domain="server/functional", priority="P1")
    async def test_multi_subpipeline_retry_all(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "multi_sub.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"subpipeline": "deploy"},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = {r["task_name"] for r in data["retry_records"]}
        assert names == {"deploy.upload", "deploy.restart"}

    @pytest.mark.zentao("TC-S0072", domain="server/functional", priority="P2")
    async def test_multi_subpipeline_dependency_tree_cross_sub(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "multi_sub.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.get(f"/api/runs/{run_id}/retry/dependency-tree?task=deploy.restart")
        assert resp.status_code == 200
        data = resp.json()
        tree = data["tree"]
        names = {n["name"] for n in tree}
        assert "deploy.upload" in names
        assert "deploy.restart" in names

    @pytest.mark.zentao("TC-S0073", domain="server/functional", priority="P1")
    async def test_diamond_retry_then_versions(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["diamond.b"], "include_upstream": True},
        )

        await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["diamond.d"], "include_upstream": True},
        )

        resp = await client.get(f"/api/runs/{run_id}/retry/versions")
        assert resp.status_code == 200
        v = resp.json()
        assert len(v["task_retries"]["diamond.a"]) == 2
        assert len(v["task_retries"]["diamond.b"]) == 2
        assert len(v["task_retries"]["diamond.c"]) == 1
        assert len(v["task_retries"]["diamond.d"]) == 1

    @pytest.mark.zentao("TC-S0074", domain="server/functional", priority="P1")
    async def test_diamond_retry_logs(self, client, setup_project, tmp_project, db_engine, clean_db):
        resp = await client.post("/api/runs/", json={"pipeline": "diamond.yaml", "params": {}})
        run_id = resp.json()["id"]
        await _wait_run_done(client, run_id)

        resp = await client.post(
            f"/api/runs/{run_id}/retry",
            json={"tasks": ["diamond.b"]},
        )
        retry_id = resp.json()["retry_records"][0]["id"]

        log_resp = await client.get(f"/api/runs/{run_id}/retry/{retry_id}/logs")
        assert log_resp.status_code == 200
        assert log_resp.json()["exists"] is True
        assert "b" in log_resp.json()["content"]

