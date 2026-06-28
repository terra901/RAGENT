"""MySQL-backed SQL template registry storage."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..core.logging import get_logger
from .sql_template_schema import SQL_TEMPLATE_DDL
from .sql_template_writer import import_registry_rows

log = get_logger(__name__)


@dataclass
class SqlTemplateSummary:
    """SQL 模板摘要。"""

    template_name: str
    name: str
    description: str
    business_description: str
    selection_guidance: str
    priority: int
    intent: str
    source_tables: list[str]
    supported_metrics: list[str]
    supported_dimensions: list[str]
    analysis_types: list[str]


class SqlTemplateStore:
    """SQL template registry storage backed by MySQL."""

    def __init__(self, database_url: str):
        self._engine: AsyncEngine = create_async_engine(database_url, echo=False, pool_pre_ping=True)

    @property
    def db_path(self) -> str:
        """返回兼容旧 stats API 的数据库标签。"""
        return "mysql:RAGENT"

    async def initialize(self) -> None:
        """创建模板元数据表。"""
        async with self._engine.begin() as conn:
            for ddl in SQL_TEMPLATE_DDL:
                await conn.execute(text(ddl))
        log.info("SqlTemplateStore ready in MySQL")

    async def close(self) -> None:
        """释放 metadata engine。"""
        await self._engine.dispose()

    async def import_registry_file(self, registry_path: str | Path) -> dict[str, Any]:
        """从 JSON 文件导入或更新注册表。"""
        path = Path(registry_path)
        registry = json.loads(path.read_text(encoding="utf-8"))
        return await self.import_registry(registry, source_path=str(path))

    async def import_registry(self, registry: dict[str, Any], *, source_path: str = "") -> dict[str, Any]:
        """从内存对象导入或更新注册表。"""
        async with self._engine.begin() as conn:
            await import_registry_rows(conn, registry, source_path)
        return await self.stats()

    async def stats(self) -> dict[str, Any]:
        """返回表计数和注册表元信息。"""
        async with self._engine.connect() as conn:
            meta = (await conn.execute(text(
                "SELECT registry_name, version, language, source_path, updated_at "
                "FROM sql_template_registry_meta ORDER BY updated_at DESC LIMIT 1"
            ))).mappings().first()
            counts = {
                "dimensions": await self._count(conn, "sql_template_dimensions"),
                "metrics": await self._count(conn, "sql_template_metrics"),
                "templates": await self._count(conn, "sql_templates"),
            }
        return {"db_path": self.db_path, "registry": dict(meta) if meta else None, **counts}

    async def _count(self, conn, table: str) -> int:
        """统计可信内部表行数。"""
        row = (await conn.execute(text(f"SELECT COUNT(*) AS n FROM {table}"))).mappings().first()
        return int(row["n"]) if row else 0

    async def list_templates(self, *, q: str | None = None, source_table: str | None = None, metric: str | None = None, dimension: str | None = None, limit: int = 100) -> list[SqlTemplateSummary]:
        """按轻量过滤条件列出模板。"""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text("SELECT * FROM sql_templates ORDER BY priority DESC, template_name ASC"))).mappings().all()
        items = [self._row_to_summary(row) for row in rows]
        if q:
            needle = q.lower()
            items = [item for item in items if needle in self._summary_text(item)]
        if source_table:
            items = [item for item in items if source_table in item.source_tables]
        if metric:
            items = [item for item in items if metric in item.supported_metrics]
        if dimension:
            items = [item for item in items if dimension in item.supported_dimensions]
        return items[: max(1, min(int(limit), 500))]

    async def get_template(self, template_name: str) -> dict[str, Any] | None:
        """按模板名返回完整 payload。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(
                text("SELECT payload_json FROM sql_templates WHERE template_name=:template_name"),
                {"template_name": template_name},
            )).mappings().first()
        return self._loads(row["payload_json"]) if row else None

    async def list_dimensions(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """返回维度 payloads。"""
        return await self._list_payloads("sql_template_dimensions", "dimension_id", limit)

    async def list_metrics(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """返回指标 payloads。"""
        return await self._list_payloads("sql_template_metrics", "metric_id", limit)

    async def _list_payloads(self, table: str, order_column: str, limit: int) -> list[dict[str, Any]]:
        """读取 JSON payload 列。"""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                text(f"SELECT payload_json FROM {table} ORDER BY {order_column} ASC LIMIT :limit"),
                {"limit": max(1, min(int(limit), 1000))},
            )).mappings().all()
        return [self._loads(row["payload_json"]) for row in rows]

    @classmethod
    def _row_to_summary(cls, row) -> SqlTemplateSummary:
        """数据库行转模板摘要。"""
        return SqlTemplateSummary(
            template_name=row["template_name"],
            name=row["name"],
            description=row["description"] or "",
            business_description=row["business_description"] or "",
            selection_guidance=row["selection_guidance"] or "",
            priority=int(row["priority"] or 0),
            intent=row["intent"] or "",
            source_tables=cls._loads(row["source_tables_json"], default=[]),
            supported_metrics=cls._loads(row["supported_metrics_json"], default=[]),
            supported_dimensions=cls._loads(row["supported_dimensions_json"], default=[]),
            analysis_types=cls._loads(row["analysis_types_json"], default=[]),
        )

    @staticmethod
    def _summary_text(item: SqlTemplateSummary) -> str:
        """拼接模板检索文本。"""
        return (item.template_name + item.name + item.description + item.business_description + item.selection_guidance).lower()

    @staticmethod
    def _loads(value: Any, default: Any | None = None) -> Any:
        """解码 MySQL JSON 列。"""
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)
