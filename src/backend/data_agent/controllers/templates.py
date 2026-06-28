"""SQL 模板控制器。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..core.config import settings
from ..models.schemas import SqlTemplateSummaryResp
from ..services import AgentRuntime
from .deps import get_runtime

router = APIRouter(prefix="/api/sql-templates", tags=["sql-templates"])


def get_sql_template_store(runtime: AgentRuntime):
    """读取 SQL 模板仓储。"""
    store = getattr(runtime, "sql_template_store", None)
    if store is None:
        raise HTTPException(status_code=404, detail="SQL 模板库未启用")
    return store


@router.get("/stats")
async def stats(runtime: AgentRuntime = Depends(get_runtime)):
    """返回 SQL 模板注册表统计。"""
    return await get_sql_template_store(runtime).stats()


@router.post("/reload")
async def reload_sql_templates(runtime: AgentRuntime = Depends(get_runtime)):
    """从配置的 JSON 注册表重新导入模板。"""
    store = get_sql_template_store(runtime)
    template_path = Path(settings.sql_template_registry_path)
    if not template_path.is_absolute():
        template_path = Path(__file__).resolve().parents[2] / template_path
    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"模板注册表不存在: {template_path}")
    return await store.import_registry_file(template_path)


@router.get("")
async def list_sql_templates(
    q: str | None = None,
    source_table: str | None = None,
    metric: str | None = None,
    dimension: str | None = None,
    limit: int = 100,
    runtime: AgentRuntime = Depends(get_runtime),
):
    """按条件列出 SQL 模板。"""
    items = await get_sql_template_store(runtime).list_templates(
        q=q,
        source_table=source_table,
        metric=metric,
        dimension=dimension,
        limit=limit,
    )
    return {"items": [SqlTemplateSummaryResp(**item.__dict__) for item in items], "total": len(items)}


@router.get("/dimensions")
async def list_dimensions(limit: int = 500, runtime: AgentRuntime = Depends(get_runtime)):
    """列出模板维度定义。"""
    items = await get_sql_template_store(runtime).list_dimensions(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/metrics")
async def list_metrics(limit: int = 500, runtime: AgentRuntime = Depends(get_runtime)):
    """列出模板指标定义。"""
    items = await get_sql_template_store(runtime).list_metrics(limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/{template_name}")
async def get_sql_template(template_name: str, runtime: AgentRuntime = Depends(get_runtime)):
    """返回单个完整 SQL 模板。"""
    item = await get_sql_template_store(runtime).get_template(template_name)
    if item is None:
        raise HTTPException(status_code=404, detail="未找到该 SQL 模板")
    return item
