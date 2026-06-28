"""连接器工厂：按 SQLAlchemy URL 协议头分发到具体实现。"""
from __future__ import annotations

from .base import BaseConnector


def make_connector(database_url: str, read_only: bool = True) -> BaseConnector:
    """构建 connector 对象或数据。"""
    head = database_url.split(":", 1)[0].lower()

    if head.startswith("sqlite"):
        from .sqlite import SQLiteConnector
        return SQLiteConnector(database_url=database_url, read_only=read_only)

    if head.startswith("postgres") or head.startswith("postgresql"):
        from .postgres import PostgresConnector
        return PostgresConnector(database_url=database_url, read_only=read_only)

    if head.startswith("mysql"):
        from .mysql import MySQLConnector
        return MySQLConnector(database_url=database_url, read_only=read_only)

    raise ValueError(
        f"未支持的数据库协议: {head!r}。当前支持 sqlite / postgresql / mysql。"
        "新增数据库请实现 BaseConnector 并在 connectors.__init__ 注册。"
    )


__all__ = ["BaseConnector", "make_connector"]
