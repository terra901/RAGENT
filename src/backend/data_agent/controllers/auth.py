"""认证控制器。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..core.auth import (
    AuthError,
    generate_token,
    hash_password,
    normalize_email,
    sha256_text,
    sign_jwt,
    validate_password,
    verify_password,
)
from ..core.config import settings
from ..models.schemas import (
    AuthLoginRequest,
    AuthPermissionsResponse,
    AuthRegisterRequest,
    AuthResponse,
    AuthUserResponse,
)
from ..storage.auth_store import AuthStore
from .deps import client_ip, get_auth_store, get_current_user, user_agent

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """转成前端可见用户字段。"""
    return {
        "id": str(user["id"]),
        "email": str(user["email"]),
        "name": str(user["name"]),
        "status": str(user["status"]),
        "is_admin": bool(user.get("is_admin")),
        "last_login_at": user.get("last_login_at"),
    }


def default_allowed_modules() -> tuple[str, ...]:
    """读取默认模块白名单。"""
    return tuple(item.strip() for item in settings.default_allowed_modules.split(",") if item.strip())


async def public_permissions(auth_store: AuthStore, user_id: str) -> dict[str, Any]:
    """确保用户有权限记录并返回公开权限。"""
    return await auth_store.ensure_permissions(user_id, allowed_modules=default_allowed_modules())


async def issue_auth_response(
    *,
    user: dict[str, Any],
    auth_store: AuthStore,
    response: Response,
    ip_address: str,
    agent: str,
    rotated: bool = False,
) -> AuthResponse:
    """签发 access token 和 refresh cookie。"""
    now = int(time.time())
    access_payload = {
        "iss": settings.jwt_issuer,
        "sub": str(user["id"]),
        "email": str(user["email"]),
        "is_admin": bool(user.get("is_admin")),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + settings.access_token_ttl_seconds,
    }
    access_token = sign_jwt(access_payload, settings.jwt_secret)
    refresh_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.refresh_token_ttl_seconds)
    await auth_store.create_refresh_session(
        token_hash=sha256_text(refresh_token),
        user_id=str(user["id"]),
        ip_address=ip_address,
        user_agent=agent,
        expires_at=expires_at,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/api/auth",
    )
    permissions = await public_permissions(auth_store, str(user["id"]))
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        rotated=rotated,
        user=AuthUserResponse(**public_user(user)),
        permissions=AuthPermissionsResponse(**permissions),
    )


def clear_refresh_cookie(response: Response) -> None:
    """清理 refresh token cookie。"""
    response.delete_cookie("refresh_token", path="/api/auth", httponly=True, samesite="lax")


@router.post("/register", response_model=AuthResponse)
async def register(req: AuthRegisterRequest, request: Request, response: Response, auth_store: AuthStore = Depends(get_auth_store)):
    """注册用户并立即登录。"""
    try:
        email = normalize_email(req.email)
        name = req.name.strip()
        if not name:
            raise AuthError("请输入姓名。", "NAME_REQUIRED")
        validate_password(req.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    try:
        user = await auth_store.create_user(
            email=email,
            password_hash=hash_password(req.password),
            name=name,
            allowed_modules=default_allowed_modules(),
        )
    except ValueError as exc:
        if str(exc) == "EMAIL_EXISTS":
            raise HTTPException(status_code=409, detail="该邮箱已注册。") from exc
        raise
    await auth_store.update_last_login(str(user["id"]))
    return await issue_auth_response(
        user=user,
        auth_store=auth_store,
        response=response,
        ip_address=client_ip(request),
        agent=user_agent(request),
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: AuthLoginRequest, request: Request, response: Response, auth_store: AuthStore = Depends(get_auth_store)):
    """校验账号密码并登录。"""
    try:
        email = normalize_email(req.email)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    user = await auth_store.find_user_by_email(email)
    if not user or not verify_password(req.password, str(user.get("password_hash") or "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误。")
    if user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号不可用，请联系管理员。")
    await auth_store.delete_refresh_sessions_for_user(str(user["id"]))
    await auth_store.update_last_login(str(user["id"]))
    fresh_user = await auth_store.find_user_by_id(str(user["id"])) or user
    return await issue_auth_response(
        user=fresh_user,
        auth_store=auth_store,
        response=response,
        ip_address=client_ip(request),
        agent=user_agent(request),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, response: Response, auth_store: AuthStore = Depends(get_auth_store)):
    """轮换 refresh token 并签发新的 access token。"""
    refresh_token = request.cookies.get("refresh_token", "")
    if not refresh_token:
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录。")
    session = await auth_store.get_refresh_session(sha256_text(refresh_token))
    if not session:
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录。")
    user = await auth_store.find_user_by_id(str(session["user_id"]))
    await auth_store.delete_refresh_session(sha256_text(refresh_token))
    if not user or user.get("status") != "active":
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用，请重新登录。")
    return await issue_auth_response(
        user=user,
        auth_store=auth_store,
        response=response,
        ip_address=client_ip(request) or str(session.get("ip_address") or ""),
        agent=user_agent(request) or str(session.get("user_agent") or ""),
        rotated=True,
    )


@router.post("/logout")
async def logout(request: Request, response: Response, auth_store: AuthStore = Depends(get_auth_store)):
    """删除当前 refresh session。"""
    refresh_token = request.cookies.get("refresh_token", "")
    if refresh_token:
        token_hash = sha256_text(refresh_token)
        session = await auth_store.get_refresh_session(token_hash)
        if session:
            await auth_store.delete_refresh_sessions_for_user(str(session["user_id"]))
        else:
            await auth_store.delete_refresh_session(token_hash)
    clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me")
async def me(current_user: dict[str, Any] = Depends(get_current_user), auth_store: AuthStore = Depends(get_auth_store)):
    """返回当前登录用户。"""
    permissions = await public_permissions(auth_store, str(current_user["id"]))
    return {"authenticated": True, "user": public_user(current_user), "permissions": permissions}
