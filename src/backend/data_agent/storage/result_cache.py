"""SQL 结果缓存：进程内 TTL + LRU。

cache key = (db_url_hash, normalized_sql_hash)
存储经过 LIMIT 校验后的 SQL → QueryResult，命中后跳过 DB 执行。
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

from ..connectors.base import QueryResult
from ..core.logging import get_logger

log = get_logger(__name__)


_WS = re.compile(r"\s+")


def _normalize_sql(sql: str) -> str:
    """统一空白 / 大小写，让等价 SQL 命中同一 cache key。"""
    return _WS.sub(" ", sql.strip().rstrip(";").strip()).strip().lower()


def _db_fingerprint(db_url: str) -> str:
    """执行 db_fingerprint 逻辑。"""
    return hashlib.sha1(db_url.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


@dataclass
class CacheStats:
    """记录缓存命中、未命中和淘汰次数。"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0


class ResultCache:
    """封装 ResultCache 的数据结构或业务行为。"""
    def __init__(self, ttl_seconds: int = 300, max_size: int = 200):
        """初始化当前对象的依赖和内部状态。"""
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._data: OrderedDict[str, tuple[float, QueryResult]] = OrderedDict()
        self.stats = CacheStats()
        self.enabled = ttl_seconds > 0 and max_size > 0

    @staticmethod
    def make_key(sql: str, db_url: str) -> str:
        """构建 key 对象或数据。"""
        normalized = _normalize_sql(sql)
        sql_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
        return f"{_db_fingerprint(db_url)}:{sql_hash}"

    def get(self, key: str) -> QueryResult | None:
        """执行 get 逻辑。"""
        if not self.enabled:
            return None
        item = self._data.get(key)
        if not item:
            self.stats.misses += 1
            return None
        ts, result = item
        if time.time() - ts > self.ttl:
            self._data.pop(key, None)
            self.stats.misses += 1
            return None
        # LRU 触碰
        self._data.move_to_end(key)
        self.stats.hits += 1
        return result

    def set(self, key: str, result: QueryResult) -> None:
        """执行 set 逻辑。"""
        if not self.enabled:
            return
        self._data[key] = (time.time(), result)
        self._data.move_to_end(key)
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)
            self.stats.evictions += 1

    def invalidate_all(self) -> None:
        """执行 invalidate_all 逻辑。"""
        self._data.clear()
