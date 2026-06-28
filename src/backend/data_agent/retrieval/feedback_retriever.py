"""Few-shot EnsembleRetriever：替换 FeedbackStore.recall 内核为 LangChain。

签名兼容：recall(question, top_k) -> list[FeedbackEntry]。
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..core.logging import get_logger
from ..observability.decorators import traced
from ..storage.feedback_bm25 import tokenize as _fb_tokenize

if TYPE_CHECKING:
    from ..storage.feedback_store import FeedbackEntry
    from .recall import EmbeddingProvider

log = get_logger(__name__)

try:
    # NOTE: Task 2 已确认 LC 1.x 把 EnsembleRetriever 移到 langchain_classic。
    # 这里用相同 import 路径以保持一致。
    from langchain_classic.retrievers.ensemble import EnsembleRetriever
    from langchain_community.vectorstores import SQLiteVec
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings as _LCEmbeddings
    from langchain_core.retrievers import BaseRetriever
    from pydantic import ConfigDict

    _HAS_VEC = True
except ImportError:
    _HAS_VEC = False
    EnsembleRetriever = None  # type: ignore
    SQLiteVec = None  # type: ignore
    Document = None  # type: ignore
    _LCEmbeddings = object  # type: ignore
    BaseRetriever = object  # type: ignore
    ConfigDict = None  # type: ignore


class _AdaptEmbedding(_LCEmbeddings):
    """把 EmbeddingProvider（encode(list[str]) -> list[list[float]]）适配为
    LangChain Embeddings 接口（embed_documents + embed_query）。
    与 retriever.py 同名 helper；为避免循环 import 在此重复定义。
    """

    def __init__(self, provider: EmbeddingProvider):
        """初始化当前对象的依赖和内部状态。"""
        super().__init__()
        self.provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """执行 embed_documents 逻辑。"""
        return self.provider.encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """执行 embed_query 逻辑。"""
        return self.provider.encode([text])[0]


class _CJKBM25Retriever(BaseRetriever):
    """轻量 CJK 友好 BM25 retriever；只供 feedback few-shot 用。

    从 FewShotEnsembleRetriever.__init__ 提升到模块级，以降低 __init__ 的
    圈复杂度（C901），并允许独立单元测试。
    """

    if _HAS_VEC:
        model_config = ConfigDict(arbitrary_types_allowed=True)
    entries: list = []  # list[FeedbackEntry]

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list:
        """获取 relevant_documents 相关数据。"""
        docs = [_fb_tokenize(e.question) for e in self.entries]
        N = len(docs)
        if N == 0:
            return []
        avgdl = sum(len(d) for d in docs) / N
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        q_tokens = _fb_tokenize(query)
        k1, b = 1.5, 0.75
        scored: list[tuple[float, object]] = []
        for e, d in zip(self.entries, docs, strict=True):
            tf: dict[str, int] = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            dl = len(d) or 1
            for t in q_tokens:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                denom = f + k1 * (1 - b + b * dl / (avgdl or 1))
                s += idf * (f * (k1 + 1)) / (denom or 1)
            if s > 0:
                scored.append((s, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        if Document is None:
            return []
        return [
            Document(page_content=e.question, metadata={"id": e.id, "sql": e.sql})
            for _, e in scored
        ]


class FewShotEnsembleRetriever:
    """FeedbackStore.recall 的替换实现。"""

    def __init__(
        self,
        entries: list[FeedbackEntry],
        embedding_provider: EmbeddingProvider | None,
        weights: tuple[float, ...],
        vec_db_path: str | None,
    ):
        """初始化当前对象的依赖和内部状态。"""
        if not _HAS_VEC:
            raise RuntimeError("FewShotEnsembleRetriever requires [vec] extras")
        self._entries_by_id = {e.id: e for e in entries}

        retrievers: list = []
        used_weights: list[float] = []

        if entries:
            bm25 = _CJKBM25Retriever(entries=entries)
            retrievers.append(bm25)
            used_weights.append(weights[0] if len(weights) >= 1 else 0.5)

            if (embedding_provider is not None and vec_db_path
                    and len(weights) >= 2):
                try:
                    docs = [
                        Document(page_content=e.question,
                                 metadata={"id": e.id, "sql": e.sql})
                        for e in entries
                    ]
                    store = SQLiteVec.from_documents(
                        docs,
                        embedding=_AdaptEmbedding(embedding_provider),
                        db_file=vec_db_path,
                        table="fewshot_vec",
                    )
                    retrievers.append(store.as_retriever(
                        search_kwargs={"k": max(5, len(docs))},
                    ))
                    used_weights.append(weights[1])
                except Exception as e:  # noqa: BLE001
                    log.warning("SQLiteVec init failed for fewshot: %s (BM25 only)", e)

        if not retrievers:
            self._ensemble = None
        elif len(retrievers) == 1:
            self._ensemble = retrievers[0]
        else:
            self._ensemble = EnsembleRetriever(
                retrievers=retrievers,
                weights=used_weights,
                id_key="id",
            )

    @traced(kind="retrieval", name="fewshot_ensemble", capture_io=False)
    def recall(self, question: str, top_k: int) -> list[FeedbackEntry]:
        """执行 recall 处理并返回结果。"""
        if self._ensemble is None:
            return []
        docs = self._ensemble.invoke(question)
        seen: list = []
        seen_ids: set[int] = set()
        for d in docs:
            eid = d.metadata.get("id")
            if eid is None or eid in seen_ids:
                continue
            entry = self._entries_by_id.get(eid)
            if entry is not None:
                seen.append(entry)
                seen_ids.add(eid)
            if len(seen) >= top_k:
                break
        return seen


__all__ = ["FewShotEnsembleRetriever", "_HAS_VEC", "_AdaptEmbedding"]
