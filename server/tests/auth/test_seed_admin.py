"""issue #204 seed admin + JWT secret 环境测试（TC-S1188 ~ TC-S1191）。

覆盖维度：环境 + 幂等 — seed admin 空表插入 / 已有数据幂等 / jwt_secret 文件生成 / 复用。
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from taskpps.auth.security import _get_jwt_secret, ensure_jwt_secret, get_secret_file_path, verify_password
from taskpps.db.engine import get_session_factory
from taskpps.main import _seed_admin_account
from taskpps.models.user import User, UserRole


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1188", domain="server/auth", priority="P0")
async def test_seed_admin_empty_db_inserts_admin(setup_project, tmp_project, db_engine):
    """空表首次 seed 应插入 admin 账号（role=admin，password=user@123 可校验）。"""
    await _seed_admin_account()
    async with get_session_factory()() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
    assert admin is not None
    assert admin.role == UserRole.ADMIN
    assert admin.is_active is True
    # 密码 user@123 可校验
    assert verify_password("user@123", admin.password_hash)


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1189", domain="server/auth", priority="P1")
async def test_seed_admin_existing_data_idempotent(setup_project, tmp_project, db_engine):
    """已有数据时再次 seed 不应重复插入 admin。"""
    # 先插入一个普通用户
    async with get_session_factory()() as session:
        from taskpps.auth.security import hash_password
        session.add(User(
            username="alice",
            nickname="Alice",
            password_hash=hash_password("pass123"),
            role=UserRole.USER,
            is_active=True,
            avatar="http://example.com/a.png",
        ))
        await session.commit()
    # 调 seed（应跳过，因已有数据）
    await _seed_admin_account()
    # 不应有 admin 账号
    async with get_session_factory()() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        # 统计总用户数
        all_users = (await session.execute(select(User))).scalars().all()
    assert admin is None  # 未 seed admin（因已有 alice）
    assert len(all_users) == 1  # 只有 alice


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1190", domain="server/auth", priority="P1")
async def test_jwt_secret_file_created(setup_project, tmp_project, db_engine):
    """ensure_jwt_secret 应在数据目录生成 jwt_secret.key 文件且非空。"""
    ensure_jwt_secret()
    secret_path = get_secret_file_path()
    assert secret_path.exists()
    content = secret_path.read_text(encoding="utf-8").strip()
    assert content, "jwt_secret.key 内容不应为空"


@pytest.mark.asyncio
@pytest.mark.zentao("TC-S1191", domain="server/auth", priority="P2")
async def test_jwt_secret_reused_when_file_exists(setup_project, tmp_project, db_engine):
    """jwt_secret.key 已存在时应复用，不重新生成。"""
    ensure_jwt_secret()
    first = _get_jwt_secret()
    # 再次调用应返回相同值
    second = _get_jwt_secret()
    assert first == second
    assert len(first) > 0
