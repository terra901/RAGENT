"""Trace 可观测控制器。"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.config import settings
from .deps import require_admin

router = APIRouter(prefix="/api", tags=["traces"])


def get_trace_store(request: Request):
    """读取 trace 存储。"""
    store = getattr(request.app.state, "trace_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="trace store unavailable")
    return store


async def list_trace_payload(request: Request, limit: int, offset: int, session_id: str | None):
    """生成 trace 列表 payload。"""
    items = await get_trace_store(request).list_traces(limit=limit, offset=offset, session_id=session_id)
    return [asdict(trace) for trace in items]


async def trace_detail_payload(trace_id: str, request: Request):
    """生成 trace 详情 payload。"""
    store = get_trace_store(request)
    trace = await store.get_trace(trace_id)
    if trace is None:
        raise HTTPException(404, "trace not found")
    spans = await store.get_spans(trace_id)
    return {"trace": asdict(trace), "spans": [asdict(span) for span in spans]}


@router.get("/admin/traces")
async def admin_list_traces(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    session_id: str | None = None,
    _admin: dict = Depends(require_admin),
):
    """后台管理列出最近 traces。"""
    return await list_trace_payload(request, limit, offset, session_id)


@router.get("/admin/traces/{trace_id}")
async def admin_get_trace(trace_id: str, request: Request, _admin: dict = Depends(require_admin)):
    """后台管理查看单条 trace 和 span 树。"""
    return await trace_detail_payload(trace_id, request)


@router.delete("/admin/traces/{trace_id}", status_code=204)
async def admin_delete_trace(trace_id: str, request: Request, _admin: dict = Depends(require_admin)):
    """后台管理删除单条 trace。"""
    await get_trace_store(request).delete_trace(trace_id)


@router.get("/traces")
async def list_traces(request: Request, limit: int = 50, offset: int = 0, session_id: str | None = None):
    """兼容旧 trace API，仍受 DA_TRACE_API_ENABLED 控制。"""
    if not settings.trace_api_enabled:
        raise HTTPException(status_code=403, detail="trace api disabled")
    return await list_trace_payload(request, limit, offset, session_id)


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request):
    """兼容旧 trace 详情 API。"""
    if not settings.trace_api_enabled:
        raise HTTPException(status_code=403, detail="trace api disabled")
    return await trace_detail_payload(trace_id, request)
