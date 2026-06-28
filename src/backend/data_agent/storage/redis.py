"""Redis 实现的 SessionStore / ResultCacheStore。"""
from __future__ import annotations

import json
import pickle
from typing import Any

from ..connectors.base import QueryResult
from ..core.logging import get_logger
from .stores import CacheStats

log = get_logger(__name__)


class RedisSessionStore:
    """会话短期记忆 Redis 实现，使用 List 保存最近 N 轮问答。"""

    def __init__(
        self,
        redis_client,
        prefix: str = "data-agent",
        ttl_seconds: int = 3600,
        max_turns_per_session: int = 20,
    ):
        """初始化当前对象的依赖和内部状态。"""
        self._redis = redis_client
        self._prefix = prefix
        self._ttl = ttl_seconds
        self._max_turns = max_turns_per_session

    def _key(self, sid: str) -> str:
        """生成会话短期记忆 key。"""
        return f"{self._prefix}:memory:short:{sid}:turns"

    async def get(self, session_id: str) -> list[dict[str, str]]:
        """读取会话历史。"""
        rows = await self._redis.lrange(self._key(session_id), 0, -1)
        if not rows:
            return []
        history: list[dict[str, str]] = []
        for raw in rows:
            try:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                item = json.loads(raw)
                if isinstance(item, dict):
                    history.append(item)
            except Exception as e:  # noqa: BLE001
                log.warning("反序列化 session %s 失败: %s", session_id, e)
        return history

    async def append(self, session_id: str, question: str, answer: str) -> None:
        """追加一轮问答，裁剪到最近 N 轮并刷新 TTL。"""
        key = self._key(session_id)
        item = json.dumps(
            {"question": question, "answer": answer},
            ensure_ascii=False,
        )
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.rpush(key, item)
            pipe.ltrim(key, -self._max_turns, -1)
            pipe.expire(key, self._ttl)
            await pipe.execute()
        except Exception as e:  # noqa: BLE001
            log.warning("写入 session %s 失败: %s", session_id, e)

    async def clear(self, session_id: str) -> None:
        """清空会话历史。"""
        await self._redis.delete(self._key(session_id))


class RedisResultCache:
    """结果缓存 Redis 实现，值为 pickle(QueryResult)。"""

    def __init__(
        self,
        redis_client,
        prefix: str = "data-agent",
        ttl_seconds: int = 300,
    ):
        """初始化当前对象的依赖和内部状态。"""
        self._redis = redis_client
        self._prefix = prefix
        self._ttl = ttl_seconds
        self.stats = CacheStats()
        self.enabled = ttl_seconds > 0

    def _key(self, key: str) -> str:
        """生成结果缓存 key。"""
        return f"{self._prefix}:cache:result:{key}"

    @staticmethod
    def make_key(sql: str, db_url: str) -> str:
        """根据 SQL 和数据库连接生成缓存 key。"""
        from .result_cache import ResultCache

        return ResultCache.make_key(sql, db_url)

    async def get(self, key: str) -> QueryResult | None:
        """读取缓存结果。"""
        if not self.enabled:
            return None
        raw: Any = await self._redis.get(self._key(key))
        if raw is None:
            self.stats.misses += 1
            return None
        try:
            obj = pickle.loads(raw)
        except Exception as e:  # noqa: BLE001
            log.warning("反序列化 cache %s 失败: %s", key, e)
            await self._redis.delete(self._key(key))
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return obj

    async def set(self, key: str, result: QueryResult) -> None:
        """写入缓存结果。"""
        if not self.enabled:
            return
        try:
            await self._redis.set(
                self._key(key),
                pickle.dumps(result),
                ex=self._ttl,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("写入 cache %s 失败: %s", key, e)

    async def invalidate_all(self) -> None:
        """清空当前 prefix 下的结果缓存。"""
        pattern = f"{self._prefix}:cache:result:*"
        async for k in self._redis.scan_iter(match=pattern, count=200):
            await self._redis.delete(k)


async def make_redis_client(url: str):
    """按 URL 创建一个 async redis 客户端。"""
    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "redis 未安装。请在 requirements.txt 中启用 redis 后运行 "
            "`pip install -r requirements.txt`。"
        ) from e

    client = redis_async.from_url(url, decode_responses=False)
    await client.ping()
    return client
