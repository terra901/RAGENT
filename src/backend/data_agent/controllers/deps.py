"""FastAPI 控制器共享依赖。"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from ..core.auth import AuthError, verify_jwt
from ..core.config import settings
from ..services import AgentRuntime
from ..storage.auth_store import AuthStore


def get_auth_store(request: Request) -> AuthStore:
    """从应用状态读取认证仓储。"""
    auth_store: AuthStore | None = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="认证服务未初始化")
    return auth_store


def get_runtime(request: Request) -> AgentRuntime:
    """从应用状态读取当前运行时。"""
    runtime: AgentRuntime | None = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="运行时未初始化")
    return runtime


def client_ip(request: Request) -> str:
    """读取真实客户端 IP，优先使用代理头。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def user_agent(request: Request) -> str:
    """读取 User-Agent 并限制长度。"""
    return request.headers.get("user-agent", "")[:512]


def bearer_token(request: Request) -> str:
    """解析 Authorization: Bearer <token>。"""
    header = request.headers.get("authorization", "")
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


async def get_current_user(
    request: Request,
    auth_store: AuthStore = Depends(get_auth_store),
) -> dict[str, Any]:
    """认证 Bearer access token 并返回当前用户。"""
    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = verify_jwt(token, settings.jwt_secret, issuer=settings.jwt_issuer)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc
    user_id = str(payload.get("sub") or "")
    user = await auth_store.find_user_by_id(user_id)
    if not user or user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用，请重新登录")
    return user


async def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """要求当前用户是管理员。"""
    if not bool(current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


async def require_module(
    user: dict[str, Any],
    auth_store: AuthStore,
    module_name: str,
) -> None:
    """检查用户 allowed_modules 中是否包含指定模块。"""
    if bool(user.get("is_admin")):
        return
    permissions = await auth_store.ensure_permissions(
        str(user["id"]),
        allowed_modules=settings.default_allowed_modules.split(","),
    )
    if module_name not in permissions.get("allowed_modules", []):
        raise HTTPException(status_code=403, detail=f"无权访问模块: {module_name}")
