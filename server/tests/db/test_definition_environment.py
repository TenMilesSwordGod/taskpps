from __future__ import annotations

import pytest
from sqlmodel import SQLModel

from taskpps.db.engine import get_engine, get_session_factory
from taskpps.models.definition import PipelineDefinition
from taskpps.models.run import PipelineRun


class TestPipelineDefinitionEnvironment:
    def test_pipeline_definition_model_in_sqlmodel_metadata(self):
        table_names = SQLModel.metadata.tables.keys()
        assert "pipeline_definitions" in table_names

    def test_pipeline_run_has_definition_id_field(self):
        columns = PipelineRun.__table__.columns.keys()
        assert "definition_id" in columns

    @pytest.mark.asyncio
    async def test_table_gets_created_on_startup(self, db_engine):
        engine = get_engine()
        async with engine.begin() as conn:
            tables = await conn.run_sync(lambda sync_conn: list(
                sync_conn.execute(  # type: ignore[arg-type]
                    __import__("sqlalchemy").text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            ))
        table_names = [row[0] for row in tables]
        assert "pipeline_definitions" in table_names
        assert "runs" in table_names

    @pytest.mark.asyncio
    async def test_pipeline_definitions_table_fields(self, db_engine):
        engine = get_engine()
        async with engine.begin() as conn:
            info = await conn.run_sync(lambda sync_conn: list(
                sync_conn.execute(  # type: ignore[arg-type]
                    __import__("sqlalchemy").text("PRAGMA table_info('pipeline_definitions')")
                )
            ))
        columns = {row[1]: row[2] for row in info}
        expected_columns = [
            "id", "project_id", "file_path", "name",
            "content", "raw_content", "file_hash",
            "active", "created_at", "updated_at",
        ]
        for col in expected_columns:
            assert col in columns, f"Column '{col}' missing from pipeline_definitions"

    @pytest.mark.asyncio
    async def test_runs_definition_id_column_exists(self, db_engine):
        engine = get_engine()
        async with engine.begin() as conn:
            info = await conn.run_sync(lambda sync_conn: list(
                sync_conn.execute(  # type: ignore[arg-type]
                    __import__("sqlalchemy").text("PRAGMA table_info('runs')")
                )
            ))
        columns = {row[1] for row in info}
        assert "definition_id" in columns

    @pytest.mark.asyncio
    async def test_pipeline_definitions_created_at_default(self, db_engine, clean_db):
        async with get_session_factory()() as session:
            from taskpps.db.repository import PipelineDefinitionRepository, ProjectRepository

            proj_repo = ProjectRepository(session)
            project = await proj_repo.create_project("/opt/p1", name="p1")

            repo = PipelineDefinitionRepository(session)
            d, _ = await repo.upsert(
                project_id=project.id,
                file_path="test.yaml",
                name="test",
                content="{}",
                raw_content="name: test\n",
                file_hash="abc12345",
            )
            assert d.created_at is not None
            assert d.updated_at is not None
            assert d.active is True
