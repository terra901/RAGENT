"""Hermes 记忆 Provider。

Hermes 是 RAGENT 的稳定记忆后备：即使没有向量库，也保留最近轮次和会话摘要；
当 embedding/sqlite-vec 可用时，再交由 CombinedMemoryProvider 承接语义召回。
"""
from __future__ import annotations

from .provider import CombinedMemoryProvider


class HermesMemoryProvider(CombinedMemoryProvider):
    """摘要 + 最近窗口的 Hermes 记忆实现，vec_store 可为空。"""
