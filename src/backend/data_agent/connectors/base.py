"""数据源连接器抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnInfo:
    """描述单个数据库列的结构信息。"""
    name: str
    data_type: str
    nullable: bool = True
    default: str | None = None
    comment: str | None = None
    is_primary_key: bool = False


@dataclass
class TableInfo:
    """描述单张数据库表的结构信息。"""
    name: str
    schema: str | None = None
    columns: list[ColumnInfo] = field(default_factory=list)
    comment: str | None = None
    row_count: int | None = None


@dataclass
class QueryResult:
    """描述一次 SQL 查询返回的数据和耗时。"""
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    execution_time_ms: float


class BaseConnector(ABC):
    """所有数据源连接器的抽象基类。"""

    @abstractmethod
    async def connect(self) -> None:
        """建立底层数据库连接并完成连接级初始化。"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """释放底层数据库连接资源。"""
        ...

    @abstractmethod
    async def get_tables(self) -> list[str]:
        """获取当前数据源中可查询的表名列表。"""
        ...

    @abstractmethod
    async def get_table_info(self, table_name: str, *, with_count: bool = True) -> TableInfo:
        """读取指定表的列、注释和行数等结构信息。"""
        ...

    @abstractmethod
    async def get_all_table_info(self, *, with_count: bool = True) -> list[TableInfo]:
        """读取当前数据源中所有表的结构信息。"""
        ...

    @abstractmethod
    async def execute_query(self, sql: str, timeout: float = 30.0) -> QueryResult:
        """执行只读查询并返回统一的 QueryResult。"""
        ...

    @abstractmethod
    async def execute_explain(self, sql: str) -> QueryResult:
        """执行 explain 查询并返回执行计划。"""
        ...
