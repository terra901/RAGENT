"""Memory 子包：MemoryProvider Protocol + 3 backend + factory。"""
from .hermes import HermesMemoryProvider
from .provider import (
    CombinedMemoryProvider,
    MemoryContext,
    MemoryProvider,
    MemoryTurn,
    NullMemoryProvider,
)

__all__ = [
    "CombinedMemoryProvider",
    "HermesMemoryProvider",
    "MemoryContext",
    "MemoryProvider",
    "MemoryTurn",
    "NullMemoryProvider",
    "make_memory_provider",
]


def make_memory_provider(*, session_store, embedding_provider, summary_llm, redis_client=None):
    """Lazy factory；调用时再 import 重型依赖。"""
    from ._factory import make_memory_provider as _make
    return _make(
        session_store=session_store,
        embedding_provider=embedding_provider,
        summary_llm=summary_llm,
        redis_client=redis_client,
    )
