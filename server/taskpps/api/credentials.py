"""凭据管理 API（仅管理员可读写）。

设计决策（为什么整路由挂 admin 依赖）：
- 凭据属于安全资产，普通用户既不应读取元数据（防止摸清内网结构），也不应写入；
- GET 在 JWT 中间件层是放行的（guest 可读），所以必须由路由级 RBAC 把门，
  否则"能登录"就等价于"能看凭据列表"；
- 写操作中间件已强制 JWT（无 token 401），RBAC 再校验角色（非 admin 403）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from taskpps.auth.dependencies import require_role
from taskpps.config import get_project_workdir_by_id
from taskpps.schemas.credential import (
    CredentialCreateRequest,
    CredentialUpdateRequest,
    CredentialView,
    MessageResponse,
)
from taskpps.services import credential_service

logger = logging.getLogger("taskpps.api.credentials")

router = APIRouter(
    prefix="/credentials",
    tags=["credentials"],
    dependencies=[Depends(require_role("admin"))],
)


def _project_workdir_or_404(project_id: str) -> Path:
    workdir = get_project_workdir_by_id(project_id)
    if workdir is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return workdir


@router.get("/", response_model=list[CredentialView])
async def list_credentials(project_id: str = Query(..., description="项目 ID")):
    workdir = _project_workdir_or_404(project_id)
    return credential_service.list_credentials(workdir, project_id)


@router.post("/", response_model=CredentialView, status_code=201)
async def create_credential(body: CredentialCreateRequest):
    workdir = _project_workdir_or_404(body.project_id)
    try:
        return credential_service.create_credential(workdir, body.model_dump())
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"凭据已存在: {body.id}") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.error("创建凭据失败: project=%s id=%s", body.project_id, body.id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None


@router.put("/{project_id}/{credential_id}", response_model=CredentialView)
async def update_credential(project_id: str, credential_id: str, body: CredentialUpdateRequest):
    workdir = _project_workdir_or_404(project_id)
    # exclude_unset：区分「未提交」与「显式 null/空串」，密码留空=不改的语义依赖此信息
    updates = body.model_dump(exclude_unset=True)
    try:
        view = credential_service.update_credential(workdir, project_id, credential_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.error("更新凭据失败: project=%s id=%s", project_id, credential_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error") from None
    if view is None:
        raise HTTPException(status_code=404, detail=f"凭据不存在: {credential_id}")
    return view


@router.delete("/{project_id}/{credential_id}", response_model=MessageResponse)
async def delete_credential(project_id: str, credential_id: str):
    workdir = _project_workdir_or_404(project_id)
    referencing = credential_service.find_credential_referencing_agents(workdir, credential_id)
    if referencing:
        raise HTTPException(
            status_code=409,
            detail=f"凭据仍被 agent 引用，无法删除: {', '.join(referencing)}",
        )
    if not credential_service.delete_credential(workdir, credential_id):
        raise HTTPException(status_code=404, detail=f"凭据不存在: {credential_id}")
    logger.info("凭据已删除: project=%s id=%s", project_id, credential_id)
    return MessageResponse(message="凭据已删除")
