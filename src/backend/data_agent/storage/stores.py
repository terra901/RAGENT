"""会话与结果缓存的统一存储抽象。"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from ..connectors.base import QueryResult
from .result_cache import ResultCache as _SyncCache
from .result_cache import _db_fingerprint, _normalize_sql  # noqa: F401


class SessionStore(Protocol):
    """多轮会话历史存储接口。"""

    async def get(self, session_id: str) -> list[dict[str, str]]:
        """读取一个会话的历史问答。"""
        ...

    async def append(self, session_id: str, question: str, answer: str) -> None:
        """追加一轮问答。"""
        ...

    async def clear(self, session_id: str) -> None:
        """清空一个会话。"""
        ...


class InMemorySessionStore:
    """带 TTL 的 LRU 会话存储（进程内）。"""

    def __init__(self, max_count: int, ttl_seconds: int, max_turns_per_session: int = 20):
        """初始化当前对象的依赖和内部状态。"""
        self._max_count = max_count
        self._ttl = ttl_seconds
        self._max_turns = max_turns_per_session
        self._data: OrderedDict[str, tuple[float, list[dict[str, str]]]] = OrderedDict()

    def _purge_expired(self) -> None:
        """清理过期会话。"""
        now = time.time()
        expired = [k for k, (ts, _) in self._data.items() if now - ts > self._ttl]
        for k in expired:
            self._data.pop(k, None)

    async def get(self, session_id: str) -> list[dict[str, str]]:
        """读取一个会话的历史问答。"""
        self._purge_expired()
        item = self._data.get(session_id)
        if not item:
            return []
        self._data.move_to_end(session_id)
        return list(item[1])

    async def append(self, session_id: str, question: str, answer: str) -> None:
        """追加一轮问答。"""
        self._purge_expired()
        history = self._data.get(session_id, (0.0, []))[1]
        history.append({"question": question, "answer": answer})
        if len(history) > self._max_turns:
            history = history[-self._max_turns:]
        self._data[session_id] = (time.time(), history)
        self._data.move_to_end(session_id)
        while len(self._data) > self._max_count:
            self._data.popitem(last=False)

    async def clear(self, session_id: str) -> None:
        """清空一个会话。"""
        self._data.pop(session_id, None)


@dataclass
class CacheStats:
    """记录缓存命中、未命中和淘汰次数。"""

    hits: int = 0
    misses: int = 0
    evictions: int = 0


class ResultCacheStore(Protocol):
    """SQL 查询结果缓存接口。"""

    enabled: bool
    stats: CacheStats

    @staticmethod
    def make_key(sql: str, db_url: str) -> str:
        """根据 SQL 和数据库连接生成缓存 key。"""
        ...

    async def get(self, key: str) -> QueryResult | None:
        """读取缓存结果。"""
        ...

    async def set(self, key: str, result: QueryResult) -> None:
        """写入缓存结果。"""
        ...

    async def invalidate_all(self) -> None:
        """清空该缓存后端。"""
        ...


class InMemoryResultCache:
    """async 包装 + 内部仍是同步 OrderedDict。"""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 200):
        """初始化当前对象的依赖和内部状态。"""
        self._inner = _SyncCache(ttl_seconds=ttl_seconds, max_size=max_size)

    @property
    def enabled(self) -> bool:
        """返回缓存是否开启。"""
        return self._inner.enabled

    @property
    def stats(self) -> CacheStats:
        """返回当前进程内缓存统计。"""
        s = self._inner.stats
        return CacheStats(hits=s.hits, misses=s.misses, evictions=s.evictions)

    @staticmethod
    def make_key(sql: str, db_url: str) -> str:
        """根据 SQL 和数据库连接生成缓存 key。"""
        return _SyncCache.make_key(sql, db_url)

    async def get(self, key: str) -> QueryResult | None:
        """读取缓存结果。"""
        return self._inner.get(key)

    async def set(self, key: str, result: QueryResult) -> None:
        """写入缓存结果。"""
        self._inner.set(key, result)

    async def invalidate_all(self) -> None:
        """清空该缓存后端。"""
        self._inner.invalidate_all()
