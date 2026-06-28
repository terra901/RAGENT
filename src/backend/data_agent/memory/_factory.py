"""MemoryProvider 工厂：根据 settings + 可用依赖装配 backend。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.config import settings
from ..core.logging import get_logger
from .hermes import HermesMemoryProvider
from .provider import CombinedMemoryProvider, MemoryProvider, NullMemoryProvider

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..storage.stores import SessionStore

log = get_logger(__name__)


def make_memory_provider(
    *,
    session_store: SessionStore,
    embedding_provider,
    summary_llm: BaseChatModel,
    redis_client=None,
) -> MemoryProvider:
    """构建 memory_provider 对象或数据。"""
    if not settings.rag_enabled or not settings.memory_enabled:
        return NullMemoryProvider(session_store, recent_n=settings.session_history_turns)

    try:
        from langchain_community.vectorstores import SQLiteVec

        from ..retrieval.retriever import _AdaptEmbedding

        _has_vec = True
    except ImportError:
        SQLiteVec = None  # type: ignore[assignment, misc]
        _AdaptEmbedding = None  # type: ignore[assignment, misc]
        _has_vec = False

    vec_store = None
    if _has_vec and embedding_provider is not None:
        vec_store = _make_vec_store(SQLiteVec, _AdaptEmbedding, embedding_provider)
    else:
        log.info("Hermes memory enabled without semantic vector backend")

    summary_store = _make_summary_store(redis_client=redis_client)
    provider_class = CombinedMemoryProvider if vec_store is not None else HermesMemoryProvider
    return provider_class(
        session_store=session_store,
        summary_store=summary_store,
        vec_store=vec_store,
        summary_llm=summary_llm,
        recent_n=settings.session_history_turns,
        semantic_top_k=settings.memory_semantic_top_k,
        semantic_min_turns=settings.memory_semantic_min_turns,
        semantic_threshold=settings.memory_semantic_threshold,
        summary_max_chars=settings.memory_summary_max_chars,
        semantic_overfetch_factor=settings.memory_semantic_overfetch_factor,
        semantic_overfetch_min=settings.memory_semantic_overfetch_min,
    )


def _make_vec_store(SQLiteVec, AdaptEmbedding, embedding_provider):
    """构建可选语义记忆向量库；失败时交给 Hermes 后备。"""
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(settings.vec_db_path, check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        conn.enable_load_extension(True)
        try:
            import sqlite_vec as _sqlite_vec
            _sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
        return SQLiteVec(
            table="chat_vec",
            connection=conn,
            db_file=settings.vec_db_path,
            embedding=AdaptEmbedding(embedding_provider),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Hermes semantic vec disabled: %s", e)
        return None


def _make_summary_store(*, redis_client=None):
    """Construct SummaryStore, preferring Redis when the app already has a client."""
    from .summary_store import RedisSummaryStore, SQLiteSummaryStore

    if redis_client is not None:
        return RedisSummaryStore(
            redis_client,
            key_prefix=settings.redis_key_prefix,
            ttl_seconds=settings.session_ttl_seconds,
        )
    return SQLiteSummaryStore(db_path=settings.vec_db_path)
