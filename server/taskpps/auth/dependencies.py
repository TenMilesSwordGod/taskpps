"""依赖注入层：get_current_user / require_role（预留，本次不挂载到路由）。

设计决策：
- spec 明确要求「依赖注入层（预留，本次不挂载到路由）」。
- 这些函数供后续精细化路由级 RBAC 使用（如 /admin/users 标记 require_role("admin)）。
- 本次所有路由鉴权由中间件统一处理（GET 放行 + POST 强制），
  路由内部通过 request.state.user 直接读取，不依赖这些注入函数。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request


def get_current_user(request: Request) -> dict[str, Any]:
    """从 request.state 获取当前用户。

    中间件已设置 request.state.user：
    - 有效 token → {"sub": username, "role": ..., "exp": ..., "iat": ...}
    - 无/无效 token（GET） → {"role": "guest"}

    预留供后续路由 Depends(get_current_user) 使用，本次不挂载。
    返回 401 如果完全无 user state（异常情况）。
    """
    user_state = getattr(request.state, "user", None)
    if not user_state:
        raise HTTPException(status_code=401, detail="未登录")
    return user_state


def require_role(role: str):  # type: ignore[no-untyped-def]
    """角色校验依赖工厂：require_role("admin") 返回一个依赖函数。

    用法（后续迭代）：
        @router.post("/admin/users", dependencies=[Depends(require_role("admin"))])
        async def create_user(...): ...

    本次不挂载到任何路由（spec 要求），仅预留。
    """

    def _check_role(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_role = user.get("role", "guest")
        if user_role != role:
            raise HTTPException(status_code=403, detail=f"需要 {role} 角色")
        return user

    return _check_role
