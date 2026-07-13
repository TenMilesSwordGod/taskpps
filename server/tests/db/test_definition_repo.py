from __future__ import annotations

import pytest

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import PipelineDefinitionRepository, ProjectRepository


class TestPipelineDefinitionRepository:
    @pytest.mark.asyncio
    async def test_upsert_new(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            definition, created = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\n",
                file_hash="abc12345",
            )
            assert created is True
            assert definition.id is not None
            assert len(definition.id) == 12
            assert definition.project_id == project.id
            assert definition.file_path == "deploy.yaml"
            assert definition.name == "deploy"
            assert definition.content == '{"name": "deploy"}'
            assert definition.raw_content == "name: deploy\n"
            assert definition.file_hash == "abc12345"
            assert definition.active is True

    @pytest.mark.asyncio
    async def test_upsert_same_hash_skip(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d1, c1 = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\n",
                file_hash="abc12345",
            )
            assert c1 is True

            d2, c2 = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\n",
                file_hash="abc12345",
            )
            assert c2 is False
            assert d2.id == d1.id

    @pytest.mark.asyncio
    async def test_upsert_hash_changed_update(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d1, c1 = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\n",
                file_hash="abc12345",
            )
            assert c1 is True

            d2, c2 = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy", "tasks": [{"name": "step1"}]}',
                raw_content="name: deploy\ntasks:\n  - name: step1\n",
                file_hash="xyz67890",
            )
            assert c2 is True
            assert d2.id == d1.id
            assert d2.file_hash == "xyz67890"
            assert d2.content == '{"name": "deploy", "tasks": [{"name": "step1"}]}'

    @pytest.mark.asyncio
    async def test_upsert_after_deactivate_new_uuid(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d1, c1 = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\n",
                file_hash="abc12345",
            )
            assert c1 is True

            d1.active = False
            await session.commit()

            d2, c2 = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content='{"name": "deploy"}',
                raw_content="name: deploy\n",
                file_hash="abc12345",
            )
            assert c2 is True
            assert d2.id != d1.id

    @pytest.mark.asyncio
    async def test_deactivate_others(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d1, _ = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            d2, _ = await repo.upsert(
                project_id=project.id,
                file_path="simple.yaml",
                name="simple",
                content="{}",
                raw_content="",
                file_hash="bbb",
            )
            d3, _ = await repo.upsert(
                project_id=project.id,
                file_path="build.yaml",
                name="build",
                content="{}",
                raw_content="",
                file_hash="ccc",
            )
            assert d1.active is True
            assert d2.active is True
            assert d3.active is True

            count = await repo.deactivate_others(project.id, {"deploy.yaml"})
            assert count == 2

            refreshed_d1 = await repo.get(d1.id)
            refreshed_d2 = await repo.get(d2.id)
            refreshed_d3 = await repo.get(d3.id)
            assert refreshed_d1.active is True
            assert refreshed_d2.active is False
            assert refreshed_d3.active is False

    @pytest.mark.asyncio
    async def test_get(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d, _ = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            fetched = await repo.get(d.id)
            assert fetched is not None
            assert fetched.id == d.id
            assert fetched.file_path == "deploy.yaml"

    @pytest.mark.asyncio
    async def test_get_not_found(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            result = await repo.get("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_by_project_and_file(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d, _ = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            found = await repo.get_by_project_and_file(project.id, "deploy.yaml")
            assert found is not None
            assert found.id == d.id

    @pytest.mark.asyncio
    async def test_get_by_project_and_file_not_found(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            found = await repo.get_by_project_and_file(project.id, "nonexistent.yaml")
            assert found is None

    @pytest.mark.asyncio
    async def test_get_by_project_and_file_inactive_not_returned(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d, _ = await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            d.active = False
            await session.commit()

            found = await repo.get_by_project_and_file(project.id, "deploy.yaml")
            assert found is None

    @pytest.mark.asyncio
    async def test_list_by_project(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            await repo.upsert(
                project_id=project.id,
                file_path="simple.yaml",
                name="simple",
                content="{}",
                raw_content="",
                file_hash="bbb",
            )

            results = await repo.list_by_project(project.id)
            assert len(results) == 2
            assert results[0].file_path == "deploy.yaml"
            assert results[1].file_path == "simple.yaml"

    @pytest.mark.asyncio
    async def test_list_by_project_active_only(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            await repo.upsert(
                project_id=project.id,
                file_path="deploy.yaml",
                name="deploy",
                content="{}",
                raw_content="",
                file_hash="aaa",
            )
            d2, _ = await repo.upsert(
                project_id=project.id,
                file_path="simple.yaml",
                name="simple",
                content="{}",
                raw_content="",
                file_hash="bbb",
            )
            d2.active = False
            await session.commit()

            results = await repo.list_by_project(project.id, active_only=True)
            assert len(results) == 1
            assert results[0].file_path == "deploy.yaml"

            results_all = await repo.list_by_project(project.id, active_only=False)
            assert len(results_all) == 2
