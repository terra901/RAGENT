"""SQLite 连接器实现。"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ..connectors.base import BaseConnector, ColumnInfo, QueryResult, TableInfo
from ..core.logging import get_logger
from ..observability.decorators import traced

log = get_logger(__name__)

# SQLite 合法标识符：字母/数字/下划线开头，不允许特殊字符。
# 这样可以杜绝在 PRAGMA / COUNT(*) 里拼接表名造成的注入面。
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ensure_safe_identifier(name: str) -> str:
    """校验输入安全性并返回可继续使用的值。"""
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"非法的 SQLite 标识符: {name!r}")
    return name


class SQLiteConnector(BaseConnector):
    """封装 SQLiteConnector 的数据结构或业务行为。"""
    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///data.db",
        read_only: bool = True,
    ):
        """初始化当前对象的依赖和内部状态。"""
        self._database_url = database_url
        self._read_only = read_only
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker | None = None

    async def connect(self) -> None:
        """建立连接。

        只读策略（避免 SQLAlchemy + Windows + `file:...?mode=ro&uri=true` 路径拼接
        的兼容性陷阱）：每次新连接挂载 `PRAGMA query_only = ON`。
        这是 SQLite **会话级**只读 —— 任何 INSERT/UPDATE/DELETE/DDL 都会被
        `attempt to write a readonly database` 拒绝，等价于 `mode=ro` URI 的效果，
        但不会因为路径含 `:` / 空格 / Windows 盘符而打不开库。
        """
        url = make_url(self._database_url)
        self._engine = create_async_engine(url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        if self._read_only and url.drivername.startswith("sqlite"):
            self._install_read_only_pragma()

        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info(
            "SQLite connected: %s (read_only=%s)",
            url.render_as_string(hide_password=True),
            self._read_only,
        )

    def _install_read_only_pragma(self) -> None:
        """在 sync 引擎的 connect 事件上挂 PRAGMA query_only = ON。

        每次 aiosqlite 新建底层 sqlite3 连接都会触发，确保整个连接池只读。
        :memory: 库也会被设为只读 —— 调用方有写需求时不要设 read_only=True。
        """
        assert self._engine is not None

        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_query_only(dbapi_conn: Any, _conn_record: Any) -> None:
            """设置 query_only 相关状态。"""
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA query_only = ON;")
            finally:
                cur.close()

    async def disconnect(self) -> None:
        """释放底层数据库连接资源。"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None

    async def get_tables(self) -> list[str]:
        """获取当前数据源中可查询的表名列表。"""
        rows = await self._execute_raw(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '\\_%' ESCAPE '\\' ORDER BY name"
        )
        return [r[0] for r in rows]

    async def get_table_info(self, table_name: str, *, with_count: bool = True) -> TableInfo:
        """读取指定表的列、注释和行数等结构信息。"""
        ident = _ensure_safe_identifier(table_name)

        col_rows = await self._execute_raw(f'PRAGMA table_info("{ident}")')
        columns = []
        for row in col_rows:
            columns.append(
                ColumnInfo(
                    name=row[1],
                    data_type=row[2],
                    nullable=not row[3],
                    default=row[4],
                    is_primary_key=bool(row[5]),
                )
            )

        row_count: int | None = None
        if with_count:
            try:
                count_rows = await self._execute_raw(f'SELECT COUNT(*) FROM "{ident}"')
                row_count = count_rows[0][0] if count_rows else None
            except Exception as e:  # noqa: BLE001
                log.warning("COUNT(*) failed for %s: %s", ident, e)

        return TableInfo(name=table_name, columns=columns, row_count=row_count)

    async def get_all_table_info(self, *, with_count: bool = True) -> list[TableInfo]:
        """读取当前数据源中所有表的结构信息。"""
        tables = await self.get_tables()
        # 并行获取，避免启动期 N+1 串行
        tasks = [self.get_table_info(t, with_count=with_count) for t in tables]
        return await asyncio.gather(*tasks)

    @traced(kind="sql_exec")
    async def execute_query(self, sql: str, timeout: float = 30.0) -> QueryResult:
        """执行只读查询并返回统一的 QueryResult。"""
        start = time.perf_counter()
        rows = await self._execute_raw(sql, timeout=timeout)
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
        rows = await self._execute_raw(f"EXPLAIN QUERY PLAN {sql}")
        return QueryResult(
            columns=[],
            rows=[tuple(r) for r in rows],
            row_count=len(rows),
            execution_time_ms=0,
        )

    async def _execute_raw(self, sql: str, timeout: float | None = None):
        """异步执行 execute_raw 逻辑。"""
        assert self._engine, "Not connected. Call connect() first."

        async def _run():
            """异步执行 run 逻辑。"""
            async with self._engine.connect() as conn:
                result = await conn.execute(text(sql))
                return result.fetchall()

        if timeout and timeout > 0:
            return await asyncio.wait_for(_run(), timeout=timeout)
        return await _run()
