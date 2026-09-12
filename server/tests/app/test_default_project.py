"""v3 (2026-09): 默认项目自动注册（_ensure_default_project）测试。

覆盖：配置 workdir / server_home / TASKPPS_SERVER_HOME 三种来源、
幂等、inactive 重新激活、以及相对路径/目录不存在时安全跳过。
"""

from __future__ import annotations

import pytest

from taskpps.main import _ensure_default_project


@pytest.fixture
def settings(setup_project):
    """返回当前测试的 settings（setup_project autouse 已加载 tmp_project 配置）。"""
    from taskpps.config import get_settings

    return get_settings()


async def _list_projects():
    from taskpps.db.engine import get_session_factory
    from taskpps.db.repository import ProjectRepository

    async with get_session_factory()() as session:
        return list(await ProjectRepository(session).list_projects(active_only=False))


@pytest.mark.asyncio
async def test_config_workdir_registers_project(settings, tmp_path, db_engine):
    """settings.workdir 配置存在 → 注册项目并自动创建 pipelines/"""
    workdir = tmp_path / "deploy-root"
    workdir.mkdir()
    settings.workdir = str(workdir)

    await _ensure_default_project()

    projects = await _list_projects()
    assert len(projects) == 1
    assert projects[0].workdir == str(workdir.resolve())
    assert projects[0].name == "deploy-root"
    assert projects[0].active is True
    assert (workdir / "pipelines").is_dir()


@pytest.mark.asyncio
async def test_idempotent_second_call(settings, tmp_path, db_engine):
    """连续两次启动调用 → 不会重复注册，id 保持不变"""
    workdir = tmp_path / "deploy-root"
    workdir.mkdir()
    settings.workdir = str(workdir)

    await _ensure_default_project()
    first = (await _list_projects())[0]
    await _ensure_default_project()

    projects = await _list_projects()
    assert len(projects) == 1
    assert projects[0].id == first.id


@pytest.mark.asyncio
async def test_no_config_skips(settings, db_engine, monkeypatch):
    """未配置 workdir/server_home 且无 TASKPPS_SERVER_HOME → 跳过（dev 安全）"""
    monkeypatch.delenv("TASKPPS_SERVER_HOME", raising=False)
    settings.workdir = None
    settings.server_home = None

    await _ensure_default_project()

    assert await _list_projects() == []


@pytest.mark.asyncio
async def test_server_home_env_fallback(settings, tmp_path, db_engine, monkeypatch):
    """存量部署兜底：仅设置 TASKPPS_SERVER_HOME 环境变量也能注册"""
    workdir = tmp_path / "opt-taskpps"
    workdir.mkdir()
    settings.workdir = None
    settings.server_home = None
    monkeypatch.setenv("TASKPPS_SERVER_HOME", str(workdir))

    await _ensure_default_project()

    projects = await _list_projects()
    assert len(projects) == 1
    assert projects[0].workdir == str(workdir.resolve())


@pytest.mark.asyncio
async def test_server_home_config_fallback(settings, tmp_path, db_engine, monkeypatch):
    """settings.server_home 配置也能作为默认项目路径（workdir 未设置时）"""
    workdir = tmp_path / "server-home"
    workdir.mkdir()
    monkeypatch.delenv("TASKPPS_SERVER_HOME", raising=False)
    settings.workdir = None
    settings.server_home = str(workdir)

    await _ensure_default_project()

    projects = await _list_projects()
    assert len(projects) == 1
    assert projects[0].workdir == str(workdir.resolve())


@pytest.mark.asyncio
async def test_relative_path_skipped(settings, db_engine):
    """相对路径 → 只告警不注册，不抛异常"""
    settings.workdir = "relative/path"

    await _ensure_default_project()

    assert await _list_projects() == []


@pytest.mark.asyncio
async def test_missing_dir_skipped(settings, tmp_path, db_engine):
    """目录不存在 → 跳过（不自动创建目录树）"""
    settings.workdir = str(tmp_path / "does-not-exist")

    await _ensure_default_project()

    assert await _list_projects() == []


@pytest.mark.asyncio
async def test_inactive_existing_project_reactivated(settings, tmp_path, db_engine):
    """已存在但 inactive 的项目 → 重新激活而不是新建"""
    from taskpps.db.engine import get_session_factory
    from taskpps.db.repository import ProjectRepository

    workdir = tmp_path / "deploy-root"
    workdir.mkdir()
    settings.workdir = str(workdir)

    async with get_session_factory()() as session:
        repo = ProjectRepository(session)
        project = await repo.create_project(workdir=str(workdir.resolve()), name="old")
        await repo.update_project(project.id, active=False)

    await _ensure_default_project()

    projects = await _list_projects()
    assert len(projects) == 1
    assert projects[0].id == project.id
    assert projects[0].active is True
