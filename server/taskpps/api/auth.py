"""认证 API 路由：注册/登录/登出/获取当前用户/修改密码。

设计决策：
- 路由前缀 /api/v1/auth（spec 要求），与现有 /api/* 路由共存。
- register/login 在中间件白名单内（无需 token）；
  logout/me/change-password 依赖中间件已校验的 request.state.user。
- 注册成功不自动登录（spec 明确：返回成功，引导去登录页）。
- 登录返回 JWT + 用户信息（前端存 localStorage）。
- logout 后端 no-op（spec 明确：前端清 localStorage 即可，不强制黑名单）。
- 错误码：401（未认证/密码错） / 409（用户名冲突） / 400（参数校验）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, update

from taskpps.auth.security import (
    create_access_token,
    generate_avatar_url,
    hash_password,
    verify_password,
)
from taskpps.config import get_settings
from taskpps.db.engine import get_session_factory
from taskpps.models.user import User, UserRole

logger = logging.getLogger("taskpps.api.auth")

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ---------- 请求/响应 Schema ----------


class RegisterRequest(BaseModel):
    """注册请求：仅用户名 + 昵称 + 密码（issue #204 评论5要求，无邮箱）。"""

    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    nickname: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)


class LoginRequest(BaseModel):
    """登录请求：用户名 + 密码 + 记住我（30天免登录）。"""

    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=64)
    remember_me: bool = False


class ChangePasswordRequest(BaseModel):
    """修改密码请求：旧密码 + 新密码。"""

    old_password: str = Field(..., min_length=1, max_length=64)
    new_password: str = Field(..., min_length=6, max_length=64)


class UserResponse(BaseModel):
    """用户信息响应（不含 password_hash，保护隐私）。

    顶部显示用 nickname（不显示 username），保护隐私。
    """

    id: int
    username: str
    nickname: str
    role: str
    avatar: str
    is_active: bool


class LoginResponse(BaseModel):
    """登录响应：JWT token + 用户信息。"""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    """通用消息响应。"""

    message: str


# ---------- 工具函数 ----------


def _user_to_response(user: User) -> UserResponse:
    """User 模型转响应模型（剥离 password_hash）。"""
    return UserResponse(
        id=user.id,  # type: ignore[arg-type]
        username=user.username,
        nickname=user.nickname,
        role=user.role.value,
        avatar=user.avatar,
        is_active=user.is_active,
    )


def _get_username_from_state(request: Request) -> str | None:
    """从 request.state.user 取 username（JWT payload 的 sub 字段）。

    中间件已保证 request.state.user 存在：
    - 有效 token → {"sub": username, "role": ..., ...}
    - 无/无效 token（GET） → {"role": "guest"}
    返回 None 表示未登录（guest）。
    """
    user_state = getattr(request.state, "user", None)
    if not user_state:
        return None
    return user_state.get("sub")


# ---------- 路由 ----------


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest) -> UserResponse:
    """注册新用户。

    - 仅接受 username + nickname + password 三字段（无邮箱等冗余字段）。
    - 密码 bcrypt 加密存储。
    - 默认 role=user, is_active=true。
    - avatar 随机生成（dicebear shapes，seed=username 保证稳定）。
    - 注册成功不自动登录（spec 明确：引导去登录页）。
    """
    try:
        async with get_session_factory()() as session:
            # 检查用户名是否已存在（唯一约束兜底，提前给出友好错误）
            existing = await session.execute(select(User).where(User.username == body.username))
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail="该用户名已被注册")

            user = User(
                username=body.username,
                nickname=body.nickname,
                password_hash=hash_password(body.password),
                role=UserRole.USER,
                is_active=True,
                avatar=generate_avatar_url(body.username),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("用户注册成功: username=%s id=%s", user.username, user.id)
            return _user_to_response(user)
    except HTTPException:
        raise
    except IntegrityError:
        # 并发注册竞态：多个请求同时通过 SELECT 存在性检查后并发 INSERT，
        # 触发 UNIQUE 约束。单独捕获返回 409，避免被通用 except 误转 500。
        # 这是 check-then-insert 模式下唯一约束的兜底，保证至多 1 个成功。
        logger.warning("注册并发冲突(UNIQUE): username=%s", body.username)
        raise HTTPException(status_code=409, detail="该用户名已被注册") from None
    except Exception:
        logger.error("注册失败: username=%s", body.username, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    """登录：校验用户名密码，成功后签发 JWT。

    - 返回 JWT（含 username/role/exp）+ 用户信息。
    - 密码错误或用户不存在统一返回 401（防用户名枚举）。
    - 账号被禁用（is_active=false）返回 403。
    """
    try:
        async with get_session_factory()() as session:
            result = await session.execute(select(User).where(User.username == body.username))
            user = result.scalar_one_or_none()

            # 用户不存在或密码错误：统一 401（防枚举）
            if user is None or not verify_password(body.password, user.password_hash):
                raise HTTPException(status_code=401, detail="用户名或密码错误")

            # 账号被禁用
            if not user.is_active:
                raise HTTPException(status_code=403, detail="账号已被禁用")

            settings = get_settings()
            # remember_me=True 时使用 long_expire_hours（30天），否则用默认 expire_hours（24h）
            expire_hours = (
                settings.jwt.long_expire_hours if body.remember_me else settings.jwt.expire_hours
            )
            token = create_access_token(
                username=user.username,
                role=user.role.value,
                expires_hours=expire_hours,
            )
            logger.info("用户登录成功: username=%s", user.username)
            return LoginResponse(access_token=token, user=_user_to_response(user))
    except HTTPException:
        raise
    except Exception:
        logger.error("登录失败: username=%s", body.username, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request) -> MessageResponse:
    """登出：后端 no-op（spec 明确：前端清 localStorage 即可，不强制黑名单）。

    依赖中间件已校验 JWT（POST 请求强制鉴权）。
    """
    username = _get_username_from_state(request)
    logger.info("用户登出: username=%s", username)
    return MessageResponse(message="已登出")


@router.get("/me", response_model=UserResponse)
async def get_current_user(request: Request) -> UserResponse:
    """获取当前登录用户信息。

    /me 是 GET 请求，中间件会放行但可能设置 guest（无 token 时）。
    此处检查 request.state.user，guest → 401。
    """
    username = _get_username_from_state(request)
    if username is None:
        raise HTTPException(status_code=401, detail="未登录")

    try:
        async with get_session_factory()() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                # token 有效但用户已被删除
                raise HTTPException(status_code=401, detail="用户不存在")
            return _user_to_response(user)
    except HTTPException:
        raise
    except Exception:
        logger.error("获取当前用户失败: username=%s", username, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.post("/change-password", response_model=MessageResponse)
async def change_password(body: ChangePasswordRequest, request: Request) -> MessageResponse:
    """修改密码：校验旧密码 + 设置新密码（bcrypt 重新加密）。

    依赖中间件已校验 JWT（POST 请求强制鉴权）。
    新密码与旧密码相同时返回 400（避免无意义更新）。
    """
    username = _get_username_from_state(request)
    if username is None:
        raise HTTPException(status_code=401, detail="未登录")

    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

    try:
        async with get_session_factory()() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=401, detail="用户不存在")

            if not verify_password(body.old_password, user.password_hash):
                raise HTTPException(status_code=401, detail="旧密码错误")

            # 原子 UPDATE WHERE password_hash = 旧 hash：避免 check-then-update 竞态。
            # 并发时第一个请求改完后 DB 中 password_hash 已变，其余请求的 UPDATE
            # 命中 0 行（rowcount != 1）→ 返回 401，保证至多 1 个成功。
            # 用读到的 user.password_hash 作乐观锁版本号，无需额外 version 字段。
            new_hash = hash_password(body.new_password)
            now = datetime.now(timezone.utc)
            stmt = (
                update(User)
                .where(User.id == user.id, User.password_hash == user.password_hash)
                .values(password_hash=new_hash, updated_at=now)
            )
            exec_result = await session.execute(stmt)
            if exec_result.rowcount != 1:
                # 并发改密竞态：旧密码已被其他请求修改，当前 hash 不再匹配
                raise HTTPException(status_code=401, detail="旧密码错误")
            await session.commit()
            logger.info("用户修改密码成功: username=%s", username)
            return MessageResponse(message="密码修改成功")
    except HTTPException:
        raise
    except Exception:
        logger.error("修改密码失败: username=%s", username, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None
