"""系统健康和 Schema 控制器。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.config import settings
from ..models.schemas import HealthResponse, SchemaColumnResp, SchemaResp, SchemaTableResp
from ..services import AgentRuntime
from .deps import get_runtime

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health_check(runtime: AgentRuntime = Depends(get_runtime)):
    """返回后端存活状态和运行时诊断。"""
    tables = await runtime.schema_manager.get_all_tables()
    base = {
        "status": "ok",
        "runtime": runtime.runtime_name,
        "resume_supported": runtime.supports_resume,
        "table_count": len(tables),
    }
    if not settings.health_verbose:
        return HealthResponse(**base)
    return HealthResponse(
        **base,
        tables=tables,
        llm_model=settings.llm_model,
        llm_base_url=settings.llm_base_url,
        cache_stats={
            "hits": runtime.result_cache.stats.hits,
            "misses": runtime.result_cache.stats.misses,
            "evictions": runtime.result_cache.stats.evictions,
        },
    )


@router.get("/schema", response_model=SchemaResp)
async def get_schema(runtime: AgentRuntime = Depends(get_runtime)) -> SchemaResp:
    """返回当前运行时加载的 Schema 缓存。"""
    tables = runtime.schema_manager.list_all()
    return SchemaResp(
        tables=[
            SchemaTableResp(
                name=table.name,
                comment=table.comment,
                row_count=table.row_count,
                columns=[
                    SchemaColumnResp(
                        name=column.name,
                        data_type=column.data_type,
                        nullable=column.nullable,
                        comment=column.comment,
                        is_primary_key=column.is_primary_key,
                    )
                    for column in table.columns
                ],
            )
            for table in tables
        ]
    )
