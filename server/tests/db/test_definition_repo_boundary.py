from __future__ import annotations

import hashlib
import json

import pytest

from taskpps.db.engine import get_session_factory
from taskpps.db.repository import PipelineDefinitionRepository, ProjectRepository


class TestPipelineDefinitionRepoBoundary:
    @pytest.mark.asyncio
    async def test_file_hash_exactly_eight_chars(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            raw = "name: boundary\n"
            hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]
            assert len(hash8) == 8

            d, created = await repo.upsert(
                project_id=project.id,
                file_path="boundary.yaml",
                name="boundary",
                content=json.dumps({"name": "boundary"}),
                raw_content=raw,
                file_hash=hash8,
            )
            assert created is True
            assert d.file_hash == hash8
            assert len(d.file_hash) == 8

    @pytest.mark.asyncio
    async def test_file_hash_longer_than_eight_truncated_in_sync(self, db_engine, clean_db):
        full_hash = hashlib.sha256(b"name: test\n").hexdigest()
        assert len(full_hash) > 8

        hash8 = full_hash[:8]
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            d, _ = await repo.upsert(
                project_id=project.id,
                file_path="hash_test.yaml",
                name="hash_test",
                content=json.dumps({"name": "hash_test"}),
                raw_content="name: test\n",
                file_hash=hash8,
            )
            assert len(d.file_hash) == 8
            assert d.file_hash != full_hash

    @pytest.mark.asyncio
    async def test_empty_project_id_upsert(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            d, created = await repo.upsert(
                project_id="",
                file_path="test.yaml",
                name="test",
                content=json.dumps({"name": "test"}),
                raw_content="name: test\n",
                file_hash="abc12345",
            )
            assert created is True
            assert d.project_id == ""

    @pytest.mark.asyncio
    async def test_very_long_file_path(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            long_path = "a" * 200 + "/deeply/nested/pipeline.yaml"
            d, created = await repo.upsert(
                project_id=project.id,
                file_path=long_path,
                name="deep_pipeline",
                content=json.dumps({"name": "deep_pipeline"}),
                raw_content="name: deep_pipeline\n",
                file_hash="abc12345",
            )
            assert created is True
            assert d.file_path == long_path

    @pytest.mark.asyncio
    async def test_special_chars_in_file_path(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            special_path = "sub_dir/my pipeline (v2).yaml"
            d, created = await repo.upsert(
                project_id=project.id,
                file_path=special_path,
                name="special",
                content=json.dumps({"name": "special"}),
                raw_content="name: special\n",
                file_hash="abc12345",
            )
            assert created is True
            assert d.file_path == special_path

            found = await repo.get_by_project_and_file(project.id, special_path)
            assert found is not None
            assert found.id == d.id

    @pytest.mark.asyncio
    async def test_unicode_content(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            raw = "name: 中文管道\noptions: {}\ntasks:\n  - name: 任务1\n    command: echo 你好\n"
            hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]
            content = json.dumps({"name": "中文管道", "options": {}, "tasks": [{"name": "任务1", "command": "echo 你好"}]}, ensure_ascii=False)

            d, created = await repo.upsert(
                project_id=project.id,
                file_path="unicode.yaml",
                name="中文管道",
                content=content,
                raw_content=raw,
                file_hash=hash8,
            )
            assert created is True
            assert d.name == "中文管道"
            assert "中文管道" in d.content

    @pytest.mark.asyncio
    async def test_deactivate_others_empty_active_paths(self, db_engine, clean_db):
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
            assert d.active is True

            count = await repo.deactivate_others(project.id, set())
            assert count == 1

            refreshed = await repo.get(d.id)
            assert refreshed.active is False

    @pytest.mark.asyncio
    async def test_deactivate_others_for_project_with_no_definitions(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            repo = PipelineDefinitionRepository(session)
            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p2", name="p2")

            count = await repo.deactivate_others(project.id, {"nonexistent.yaml"})
            assert count == 0
