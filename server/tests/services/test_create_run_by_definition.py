from __future__ import annotations

import pytest

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import PipelineDefinitionRepository, ProjectRepository
from taskpps.services.pipeline_service import PipelineService


def _setup_config(tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


class TestCreateRunByDefinition:
    @pytest.mark.asyncio
    async def test_create_run_by_definition_id(self, tmp_project, db_engine, clean_db):
        _setup_config(tmp_project)

        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project(str(tmp_project), name="test-project")

        async with get_session_factory()() as session:
            def_repo = PipelineDefinitionRepository(session)
            definition, _ = await def_repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\ntasks:\n  - name: step1\n    command: echo hello\n",
                file_hash="abc12345",
            )

        svc = PipelineService()
        result = await svc.create_run(definition.id)
        assert "id" in result
        assert result["pipeline_name"] == "deploy"

        run = await svc.get_run(result["id"])
        assert run is not None
        assert run["pipeline_name"] == "deploy"

    @pytest.mark.asyncio
    async def test_create_run_definition_not_found(self, tmp_project, db_engine, clean_db):
        _setup_config(tmp_project)
        svc = PipelineService()
        with pytest.raises(ValueError, match="Definition not found"):
            await svc.create_run("nonexistent-def-id")

    @pytest.mark.asyncio
    async def test_create_run_with_params_by_definition_id(self, tmp_project, db_engine, clean_db):
        _setup_config(tmp_project)

        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project(str(tmp_project), name="test-project")

        async with get_session_factory()() as session:
            def_repo = PipelineDefinitionRepository(session)
            definition, _ = await def_repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\ntasks:\n  - name: step1\n    command: echo hello\n",
                file_hash="abc12345",
            )

        svc = PipelineService()
        params = {"config.env": {"MY_VAR": "my_value"}}
        result = await svc.create_run(definition.id, params=params)
        assert "id" in result

        run = await svc.get_run(result["id"])
        assert run is not None
        assert run["params"] == params

    @pytest.mark.asyncio
    async def test_create_run_stores_snapshot_in_db(self, tmp_project, db_engine, clean_db):
        _setup_config(tmp_project)

        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project(str(tmp_project), name="test-project")

        async with get_session_factory()() as session:
            def_repo = PipelineDefinitionRepository(session)
            definition, _ = await def_repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\ntasks:\n  - name: step1\n    command: echo hello\n",
                file_hash="abc12345",
            )

        svc = PipelineService()
        result = await svc.create_run(definition.id)
        run_id = result["id"]

        from taskpps.db.engine import get_session_factory as _gsf

        async with _gsf()() as session:
            from taskpps.db.repository import RunRepository

            run_repo = RunRepository(session)
            run = await run_repo.get_run(run_id)
            assert run is not None
            assert run.snapshot_content is not None
            assert "name: deploy" in run.snapshot_content
            assert "step1" in run.snapshot_content
            assert "echo hello" in run.snapshot_content

    # v1 (2026-09): 回归测试 — issue #210 生产运行失败
    # 生产 gunicorn 以项目根目录（/opt/taskpps）为 CWD 启动，原实现先用 CWD 解析
    # 相对 file_path 再 relative_to(pipelines)，嵌套路径会抛
    # "'test/test.yaml' is not in the subpath of '/opt/taskpps/pipelines'"。
    # 测试环境 CWD 与 tmp_project 不同，原测试无法触发，故显式 chdir 模拟生产。
    @pytest.mark.asyncio
    async def test_create_run_nested_path_when_cwd_is_workdir(self, tmp_project, db_engine, clean_db, monkeypatch):
        _setup_config(tmp_project)
        monkeypatch.chdir(tmp_project)

        nested_dir = tmp_project / "pipelines" / "test"
        nested_dir.mkdir()
        (nested_dir / "test.yaml").write_text(
            "name: nested_test\n"
            "tasks:\n"
            "  - name: step1\n"
            "    command: echo hello\n"
        )

        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project(str(tmp_project), name="test-project")

        async with get_session_factory()() as session:
            def_repo = PipelineDefinitionRepository(session)
            definition, _ = await def_repo.upsert(
                project_id=project.id,
                file_path="test/test.yaml",
                name="nested_test",
                content='{"name": "nested_test"}',
                raw_content="name: nested_test\ntasks:\n  - name: step1\n    command: echo hello\n",
                file_hash="nested01",
            )

        svc = PipelineService()
        result = await svc.create_run(definition.id)
        assert result["pipeline_name"] == "nested_test"

        from taskpps.db.engine import get_session_factory as _gsf

        async with _gsf()() as session:
            from taskpps.db.repository import RunRepository

            run = await RunRepository(session).get_run(result["id"])
            assert run is not None
            assert run.snapshot_content is not None
            assert "nested_test" in run.snapshot_content

    @pytest.mark.asyncio
    async def test_create_run_with_env_substitution_by_definition_id(self, tmp_project, db_engine, clean_db):
        _setup_config(tmp_project)

        # Write a pipeline with env variable
        env_yaml_path = tmp_project / "pipelines" / "env_test.yaml"
        env_yaml_path.write_text(
            "name: env_test\n"
            "options:\n"
            "  env:\n"
            "    WHO: ${env.MY_NAME}\n"
            "tasks:\n"
            "  - name: greet\n"
            "    command: echo hi\n"
        )

        async with get_session_factory()() as session:
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project(str(tmp_project), name="test-project")

        async with get_session_factory()() as session:
            def_repo = PipelineDefinitionRepository(session)
            definition, _ = await def_repo.upsert(
                project_id=project.id,
                file_path="env_test.yaml",
                name="env_test",
                content='{"name": "env_test"}',
                raw_content="name: env_test\noptions:\n  env:\n    WHO: ${env.MY_NAME}\ntasks:\n  - name: greet\n    command: echo hi\n",
                file_hash="xyz12345",
            )

        svc = PipelineService()
        params = {"config.env": {"MY_NAME": "World"}}
        result = await svc.create_run(definition.id, params=params)
        assert "id" in result
