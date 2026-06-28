"""SummaryStore: 累积摘要存储。

3 backend：
- InMemorySummaryStore: dict + TTL
- SQLiteSummaryStore: ./data/memory.db 单表 session_summary
- RedisSummaryStore: key 'da:summary:{session_id}'，TTL = session_ttl_seconds
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Protocol


class SummaryStore(Protocol):
    """封装 SummaryStore 的数据结构或业务行为。"""
    async def get(self, session_id: str) -> str | None:
        """异步执行 get 逻辑。"""
        ...
    async def set(self, session_id: str, summary: str) -> None:
        """异步执行 set 逻辑。"""
        ...
    async def clear(self, session_id: str) -> None:
        """异步执行 clear 逻辑。"""
        ...


class InMemorySummaryStore:
    """封装 InMemorySummaryStore 的数据结构或业务行为。"""
    def __init__(self, ttl_seconds: int = 3600):
        """初始化当前对象的依赖和内部状态。"""
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, str]] = {}

    def _expired(self, ts: float) -> bool:
        """执行 expired 逻辑。"""
        return self._ttl > 0 and (time.time() - ts) > self._ttl

    async def get(self, session_id: str) -> str | None:
        """异步执行 get 逻辑。"""
        item = self._data.get(session_id)
        if not item:
            return None
        ts, summary = item
        if self._expired(ts):
            self._data.pop(session_id, None)
            return None
        return summary

    async def set(self, session_id: str, summary: str) -> None:
        """异步执行 set 逻辑。"""
        self._data[session_id] = (time.time(), summary)

    async def clear(self, session_id: str) -> None:
        """异步执行 clear 逻辑。"""
        self._data.pop(session_id, None)


_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS session_summary (
    session_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class SQLiteSummaryStore:
    """封装 SQLiteSummaryStore 的数据结构或业务行为。"""
    def __init__(self, db_path: str):
        """初始化当前对象的依赖和内部状态。"""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        conn = sqlite3.connect(str(self._db_path))
        with conn:
            conn.executescript(_SQLITE_DDL)
        conn.close()

    def _open(self) -> sqlite3.Connection:
        """执行 open 逻辑。"""
        c = sqlite3.connect(str(self._db_path))
        c.row_factory = sqlite3.Row
        return c

    async def get(self, session_id: str) -> str | None:
        """异步执行 get 逻辑。"""
        async with self._lock:
            def _do():
                """执行 do 逻辑。"""
                with self._open() as c:
                    row = c.execute(
                        "SELECT summary FROM session_summary WHERE session_id=?",
                        (session_id,),
                    ).fetchone()
                    return row["summary"] if row else None
            return await asyncio.to_thread(_do)

    async def set(self, session_id: str, summary: str) -> None:
        """异步执行 set 逻辑。"""
        async with self._lock:
            def _do():
                """执行 do 逻辑。"""
                with self._open() as c:
                    c.execute(
                        "INSERT INTO session_summary(session_id, summary, updated_at) "
                        "VALUES(?, ?, ?) "
                        "ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, "
                        "updated_at=excluded.updated_at",
                        (session_id, summary, time.time()),
                    )
            await asyncio.to_thread(_do)

    async def clear(self, session_id: str) -> None:
        """异步执行 clear 逻辑。"""
        async with self._lock:
            def _do():
                """执行 do 逻辑。"""
                with self._open() as c:
                    c.execute("DELETE FROM session_summary WHERE session_id=?", (session_id,))
            await asyncio.to_thread(_do)


class RedisSummaryStore:
    """需要在 requirements.txt 中启用 redis。"""

    def __init__(self, client, key_prefix: str = "data-agent", ttl_seconds: int = 3600):
        """初始化当前对象的依赖和内部状态。"""
        self._redis = client
        self._prefix = key_prefix
        self._ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        """生成会话摘要 key。"""
        return f"{self._prefix}:memory:summary:{session_id}"

    async def get(self, session_id: str) -> str | None:
        """异步执行 get 逻辑。"""
        v = await self._redis.get(self._key(session_id))
        if v is None:
            return None
        return v.decode("utf-8") if isinstance(v, bytes) else str(v)

    async def set(self, session_id: str, summary: str) -> None:
        """异步执行 set 逻辑。"""
        await self._redis.set(self._key(session_id), summary, ex=self._ttl)

    async def clear(self, session_id: str) -> None:
        """异步执行 clear 逻辑。"""
        await self._redis.delete(self._key(session_id))


__all__ = [
    "SummaryStore",
    "InMemorySummaryStore",
    "SQLiteSummaryStore",
    "RedisSummaryStore",
]
