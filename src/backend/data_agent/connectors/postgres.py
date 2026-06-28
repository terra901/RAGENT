"""PostgreSQL 连接器（asyncpg via SQLAlchemy）。

注意:
- read_only 强制：使用 `default_transaction_read_only=on` 服务端参数 + 每次 BEGIN READ ONLY。
- 标识符 quoting 通过 SQLAlchemy `text(...)` 参数化避免拼接。
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ..connectors.base import BaseConnector, ColumnInfo, QueryResult, TableInfo
from ..core.logging import get_logger
from ..observability.decorators import traced

log = get_logger(__name__)


_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe(name: str) -> str:
    """校验输入安全性并返回可继续使用的值。"""
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"非法的 PG 标识符: {name!r}")
    return name


class PostgresConnector(BaseConnector):
    """封装 PostgresConnector 的数据结构或业务行为。"""
    def __init__(self, database_url: str, read_only: bool = True, schema: str = "public"):
        """初始化当前对象的依赖和内部状态。"""
        self._database_url = database_url
        self._read_only = read_only
        self._schema = _safe(schema)
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker | None = None

    def _build_url(self) -> URL:
        """构建 url 对象或数据。"""
        return make_url(self._database_url)

    async def connect(self) -> None:
        """建立底层数据库连接并完成连接级初始化。"""
        url = self._build_url()
        connect_args: dict[str, Any] = {}
        if self._read_only:
            # asyncpg server_settings 在连接建立时设置，整个连接全局只读
            connect_args["server_settings"] = {
                "default_transaction_read_only": "on",
                "application_name": "data-agent",
            }
        self._engine = create_async_engine(url, connect_args=connect_args, echo=False, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info(
            "PostgreSQL connected: %s (read_only=%s, schema=%s)",
            url.render_as_string(hide_password=True),
            self._read_only,
            self._schema,
        )

    async def disconnect(self) -> None:
        """释放底层数据库连接资源。"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    async def get_tables(self) -> list[str]:
        """获取当前数据源中可查询的表名列表。"""
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        rows = await self._execute_raw(sql, params={"schema": self._schema})
        return [r[0] for r in rows]

    async def get_table_info(self, table_name: str, *, with_count: bool = True) -> TableInfo:
        """读取指定表的列、注释和行数等结构信息。"""
        ident = _safe(table_name)

        # 列信息
        col_sql = (
            "SELECT column_name, data_type, is_nullable, column_default, "
            "COALESCE((SELECT pg_catalog.pg_get_serial_sequence(:full, column_name)), '') AS seq, "
            "ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :tbl "
            "ORDER BY ordinal_position"
        )
        col_rows = await self._execute_raw(
            col_sql,
            params={"schema": self._schema, "tbl": ident, "full": f"{self._schema}.{ident}"},
        )

        # 主键
        pk_sql = (
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = :full::regclass AND i.indisprimary"
        )
        pk_rows = await self._execute_raw(
            pk_sql, params={"full": f"{self._schema}.{ident}"}
        )
        pks = {r[0] for r in pk_rows}

        # 列注释
        comment_sql = (
            "SELECT a.attname, pg_catalog.col_description(a.attrelid, a.attnum) "
            "FROM pg_attribute a "
            "WHERE a.attrelid = :full::regclass AND a.attnum > 0 AND NOT a.attisdropped"
        )
        cmt_rows = await self._execute_raw(
            comment_sql, params={"full": f"{self._schema}.{ident}"}
        )
        col_comments = {r[0]: r[1] for r in cmt_rows if r[1]}

        columns = []
        for r in col_rows:
            cname = r[0]
            columns.append(
                ColumnInfo(
                    name=cname,
                    data_type=r[1],
                    nullable=(r[2] == "YES"),
                    default=r[3],
                    is_primary_key=(cname in pks),
                    comment=col_comments.get(cname),
                )
            )

        row_count: int | None = None
        if with_count:
            try:
                cnt = await self._execute_raw(
                    f'SELECT COUNT(*) FROM "{self._schema}"."{ident}"'
                )
                row_count = cnt[0][0] if cnt else None
            except Exception as e:  # noqa: BLE001
                log.warning("COUNT(*) failed for %s.%s: %s", self._schema, ident, e)

        # 表注释
        tbl_cmt_rows = await self._execute_raw(
            "SELECT obj_description(:full::regclass, 'pg_class')",
            params={"full": f"{self._schema}.{ident}"},
        )
        tbl_comment = tbl_cmt_rows[0][0] if tbl_cmt_rows and tbl_cmt_rows[0][0] else None

        return TableInfo(
            name=table_name,
            schema=self._schema,
            columns=columns,
            comment=tbl_comment,
            row_count=row_count,
        )

    async def get_all_table_info(self, *, with_count: bool = True) -> list[TableInfo]:
        """读取当前数据源中所有表的结构信息。"""
        tables = await self.get_tables()
        return await asyncio.gather(*[self.get_table_info(t, with_count=with_count) for t in tables])

    @traced(kind="sql_exec")
    async def execute_query(self, sql: str, timeout: float = 30.0) -> QueryResult:
        """执行只读查询并返回统一的 QueryResult。"""
        start = time.perf_counter()
        rows = await self._execute_raw(sql, timeout=timeout, read_only_tx=self._read_only)
        elapsed = (time.perf_counter() - start) * 1000

        columns: list[str] = []
        if rows:
            try:
                columns = list(rows[0]._mapping.keys())
            except AttributeError:
                pass
        return QueryResult(
            columns=columns,
            rows=[tuple(r) for r in rows],
            row_count=len(rows),
            execution_time_ms=round(elapsed, 2),
        )

    async def execute_explain(self, sql: str) -> QueryResult:
        """执行 explain 查询并返回执行计划。"""
        rows = await self._execute_raw(f"EXPLAIN {sql}")
        return QueryResult(
            columns=[],
            rows=[tuple(r) for r in rows],
            row_count=len(rows),
            execution_time_ms=0,
        )

    async def _execute_raw(
        self,
        sql: str,
        params: dict | None = None,
        timeout: float | None = None,
        read_only_tx: bool = False,
    ):
        """异步执行 execute_raw 逻辑。"""
        assert self._engine, "Not connected. Call connect() first."

        async def _run():
            """异步执行 run 逻辑。"""
            async with self._engine.connect() as conn:
                if read_only_tx:
                    # 双保险：在事务级再次声明只读
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                result = await conn.execute(text(sql), params or {})
                return result.fetchall()

        if timeout and timeout > 0:
            return await asyncio.wait_for(_run(), timeout=timeout)
        return await _run()
