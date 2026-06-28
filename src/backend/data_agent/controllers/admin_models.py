"""后台模型管理控制器。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..admin.model_connectivity import test_model_connectivity
from ..admin.model_payloads import normalize_model_payload, normalize_provider_payload, to_db_status
from ..admin.model_repository import ModelManagementRepository
from .deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin-models"])


def get_model_repo(request: Request) -> ModelManagementRepository:
    """从应用状态读取模型管理仓储。"""
    repo = getattr(request.app.state, "model_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="模型管理服务未初始化")
    return repo


def public_model(model: dict[str, Any]) -> dict[str, Any]:
    """剔除仅服务端可见的明文 Key。"""
    safe = dict(model)
    safe.pop("apiKey", None)
    return safe


@router.get("/model-providers")
async def list_providers(_admin: dict = Depends(require_admin), repo: ModelManagementRepository = Depends(get_model_repo)):
    """列出模型供应商。"""
    return {"providers": await repo.list_providers()}


@router.post("/model-providers")
async def create_provider(
    payload: dict[str, Any],
    admin: dict = Depends(require_admin),
    repo: ModelManagementRepository = Depends(get_model_repo),
):
    """创建模型供应商。"""
    try:
        provider = await repo.create_provider(normalize_provider_payload(payload), str(admin["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"provider": provider}


@router.post("/model-providers/{provider_id}")
async def update_provider(
    provider_id: str,
    payload: dict[str, Any],
    admin: dict = Depends(require_admin),
    repo: ModelManagementRepository = Depends(get_model_repo),
):
    """更新模型供应商。"""
    try:
        provider = await repo.update_provider(provider_id, normalize_provider_payload(payload), str(admin["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"provider": provider}


@router.delete("/model-providers/{provider_id}")
async def delete_provider(provider_id: str, _admin: dict = Depends(require_admin), repo: ModelManagementRepository = Depends(get_model_repo)):
    """删除模型供应商。"""
    try:
        await repo.delete_provider(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/model-providers/{provider_id}/models")
async def list_models(provider_id: str, _admin: dict = Depends(require_admin), repo: ModelManagementRepository = Depends(get_model_repo)):
    """列出供应商下的模型。"""
    return {"models": await repo.list_models(provider_id)}


@router.post("/model-providers/{provider_id}/models")
async def create_model(
    provider_id: str,
    payload: dict[str, Any],
    admin: dict = Depends(require_admin),
    repo: ModelManagementRepository = Depends(get_model_repo),
):
    """创建模型并验证 Key 连通性。"""
    try:
        data = normalize_model_payload(payload)
        if not data.get("api_key"):
            raise ValueError("API Key 不能为空。")
        provider = await repo.get_provider(provider_id)
        if not provider:
            raise ValueError("供应商不存在。")
        await ensure_connectivity(provider, data)
        model = await repo.create_model(provider_id, data, str(admin["id"]))
        await repo.update_model_test_result(model["id"], ok=True, message="模型接口真实调用成功。")
        return {"model": public_model(await repo.get_model_with_provider(model["id"]) or model)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}")
async def update_model(
    model_id: str,
    payload: dict[str, Any],
    admin: dict = Depends(require_admin),
    repo: ModelManagementRepository = Depends(get_model_repo),
):
    """更新模型信息，传入 Key 时同步验证。"""
    try:
        data = normalize_model_payload(payload)
        current = await repo.get_model_with_provider(model_id)
        if not current:
            raise ValueError("模型不存在。")
        if data.get("api_key"):
            await ensure_connectivity(current, data)
        model = await repo.update_model(model_id, data, str(admin["id"]))
        if data.get("api_key"):
            await repo.update_model_test_result(model_id, ok=True, message="模型接口真实调用成功。")
        return {"model": public_model(await repo.get_model_with_provider(model_id) or model)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/key")
async def update_model_key(
    model_id: str,
    payload: dict[str, Any],
    admin: dict = Depends(require_admin),
    repo: ModelManagementRepository = Depends(get_model_repo),
):
    """替换模型 Key，并立即测试连通性。"""
    api_key = str(payload.get("apiKey") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空。")
    current = await repo.get_model_with_provider(model_id)
    if not current:
        raise HTTPException(status_code=404, detail="模型不存在。")
    result = await test_model_connectivity({**current, "apiKey": api_key, "modelCode": current["code"]})
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Key 连通性测试未通过。")
    model = await repo.update_model_key(model_id, api_key, str(admin["id"]))
    await repo.update_model_test_result(model_id, ok=True, message=str(result.get("message") or "模型接口真实调用成功。"))
    return {"model": public_model(model)}


@router.post("/models/{model_id}/status")
async def set_model_status(
    model_id: str,
    payload: dict[str, Any],
    admin: dict = Depends(require_admin),
    repo: ModelManagementRepository = Depends(get_model_repo),
):
    """启用或禁用模型。"""
    try:
        model = await repo.set_model_status(model_id, to_db_status(str(payload.get("status") or "disabled")), str(admin["id"]))
        return {"model": public_model(model)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, _admin: dict = Depends(require_admin), repo: ModelManagementRepository = Depends(get_model_repo)):
    """删除模型。"""
    try:
        await repo.delete_model(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


async def ensure_connectivity(provider_or_model: dict[str, Any], data: dict[str, Any]) -> None:
    """调用真实模型接口并在失败时抛出 ValueError。"""
    result = await test_model_connectivity({
        "baseUrl": provider_or_model["baseUrl"],
        "timeoutSeconds": provider_or_model["timeoutSeconds"],
        "modelCode": data["model_name"],
        "apiKey": data.get("api_key") or provider_or_model.get("apiKey"),
    })
    if not result.get("ok"):
        raise ValueError(result.get("message") or "模型连通性测试未通过。")
