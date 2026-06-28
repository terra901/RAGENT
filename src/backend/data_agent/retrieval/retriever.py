"""Schema EnsembleRetriever：替换 SchemaManager._recall 内核为 LangChain。

签名兼容：recall(question, top_k) -> list[str] 表名。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict

from ..core.logging import get_logger
from ..observability.decorators import traced

if TYPE_CHECKING:
    from ..connectors.base import TableInfo
    from ..query_engine.semantic_layer import SemanticLayer
    from .recall import EmbeddingProvider

log = get_logger(__name__)


# 启动期一次性 import：未装 [vec] extras 时 _HAS_VEC=False，retriever 不构造
# EnsembleRetriever lives in langchain_classic (langchain 1.x split), not langchain.retrievers
try:
    from langchain_classic.retrievers.ensemble import EnsembleRetriever
    from langchain_community.vectorstores import SQLiteVec
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings
    from langchain_core.retrievers import BaseRetriever
    _HAS_VEC = True
except ImportError:
    _HAS_VEC = False
    EnsembleRetriever = None  # type: ignore
    SQLiteVec = None  # type: ignore
    Document = None  # type: ignore
    Embeddings = object  # type: ignore
    BaseRetriever = object  # type: ignore


def _table_to_doc(t: "TableInfo") -> "Document":
    """执行 table_to_doc 逻辑。"""
    cols = " ".join(c.name for c in t.columns)
    comment = (t.comment or "") if hasattr(t, "comment") else ""
    return Document(
        page_content=f"{t.name} {t.name.replace('_', ' ')} {cols} {comment}".strip(),
        metadata={"table": t.name},
    )


class BM25RecallerRetriever(BaseRetriever):
    """把既有 BM25Recaller 包装成 LangChain BaseRetriever。

    使用 recall.py 的 _tokenize（支持 CJK bigram），保留当所有分数为 0 时
    按 schema 顺序兜底的行为，与旧 SchemaManager._recall 完全一致。

    BM25 在 __init__（model_post_init）阶段一次性 fit，每次召回直接复用，
    避免 per-query 重新 fit 的延迟。
    """

    schema_cache: Any  # dict[str, TableInfo]
    extra_text_per_table: Any | None = None  # dict[str, str] | None
    # 预 fit 的 BM25Recaller 实例，model_post_init 后填充
    _bm25_fitted: Any = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:  # noqa: ANN001
        """在 pydantic 完成字段验证后立即 fit BM25，每次 refresh 只 fit 一次。"""
        from .recall import BM25Recaller

        bm25 = BM25Recaller()
        bm25.fit(self.schema_cache, extra_text_per_table=self.extra_text_per_table)
        object.__setattr__(self, "_bm25_fitted", bm25)

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> list["Document"]:
        """获取 relevant_documents 相关数据。"""
        scores = self._bm25_fitted.score(query)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 收集正分文档；若全为 0，按 schema 插入顺序全量返回（行为与 _recall 一致）
        has_positive = any(s > 0 for _, s in ranked)
        if has_positive:
            ordered = [name for name, s in ranked if s > 0]
        else:
            ordered = list(self.schema_cache.keys())

        return [
            Document(
                page_content=f"{name} {' '.join(c.name for c in self.schema_cache[name].columns)}",
                metadata={"table": name},
            )
            for name in ordered
            if name in self.schema_cache
        ]


class SemanticAliasRetriever(BaseRetriever):
    """语义层 alias 硬命中 retriever：question 出现某个 mapping 的 term/alias，
    则该 mapping 指向的表得分 = 1.0；不命中 = 0。Document.metadata["table"] = 表名。
    """

    semantic_layer: Any  # SemanticLayer — Any 避免 pydantic v2 前向引用问题
    schema_cache_keys: frozenset[str]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> list["Document"]:
        """获取 relevant_documents 相关数据。"""
        hits = self.semantic_layer.find_matches(query)
        out: list[Document] = []
        seen: set[str] = set()
        for m in hits:
            if m.table_name in self.schema_cache_keys and m.table_name not in seen:
                out.append(Document(
                    page_content=m.table_name,
                    metadata={"table": m.table_name},
                ))
                seen.add(m.table_name)
        return out


class SchemaEnsembleRetriever:
    """SchemaManager._recall 的替换实现。"""

    def __init__(
        self,
        schema_cache: dict[str, "TableInfo"],
        semantic_layer: "SemanticLayer | None",
        embedding_provider: "EmbeddingProvider | None",
        weights: tuple[float, ...],
        vec_db_path: str,
        extra_text_per_table: dict[str, str] | None = None,
    ):
        """初始化当前对象的依赖和内部状态。"""
        if not _HAS_VEC:
            raise RuntimeError("SchemaEnsembleRetriever requires [vec] extras")
        self._schema_keys = list(schema_cache.keys())
        retrievers: list = []
        used_weights: list[float] = []

        # 路线 1: BM25（用本地 BM25Recaller 包装，支持 CJK，保留零分兜底顺序）
        # extra_text_per_table 保证语义层别名/描述喂进 BM25 语料，与回退路径一致
        bm25_r = BM25RecallerRetriever(
            schema_cache=schema_cache,
            extra_text_per_table=extra_text_per_table,
        )
        retrievers.append(bm25_r)
        used_weights.append(weights[0] if len(weights) >= 1 else 0.4)

        # 路线 2: SQLiteVec 向量召回（需要 embedding_provider）
        if embedding_provider is not None and len(weights) >= 2:
            try:
                adapted = _AdaptEmbedding(embedding_provider)
                docs = [_table_to_doc(t) for t in schema_cache.values()]
                texts = [d.page_content for d in docs]
                metas = [d.metadata for d in docs]
                store = SQLiteVec.from_texts(
                    texts,
                    adapted,
                    metadatas=metas,
                    db_file=vec_db_path,
                    table="schema_vec",
                )
                retrievers.append(store.as_retriever(search_kwargs={"k": max(5, len(docs))}))
                used_weights.append(weights[1])
            except Exception as e:  # noqa: BLE001
                log.warning("SQLiteVec init failed for schema: %s (falling back to BM25 only)", e)

        # 路线 3: 语义层别名硬命中
        if semantic_layer is not None and len(weights) >= 3:
            sem_r = SemanticAliasRetriever(
                semantic_layer=semantic_layer,
                schema_cache_keys=frozenset(schema_cache.keys()),
            )
            retrievers.append(sem_r)
            used_weights.append(weights[2])

        if len(retrievers) == 1:
            self._ensemble = retrievers[0]
        else:
            # id_key="table": RRF deduplication by metadata["table"] so documents from
            # different retrievers (with different page_content) representing the same
            # table are scored cumulatively rather than treated as separate entries.
            self._ensemble = EnsembleRetriever(
                retrievers=retrievers, weights=used_weights, id_key="table"
            )

    @traced(kind="retrieval", name="schema_ensemble", capture_io=False)
    def recall(self, question: str, top_k: int) -> list[str]:
        """执行 recall 处理并返回结果。"""
        docs = self._ensemble.invoke(question)
        seen: dict[str, None] = {}
        for d in docs:
            tbl = d.metadata.get("table")
            if not tbl or tbl not in self._schema_keys:
                continue
            seen.setdefault(tbl, None)
            if len(seen) >= top_k:
                break
        # 兜底：若 ensemble 没有任何有效命中，按 schema 键顺序返回
        if not seen:
            return self._schema_keys[:top_k]
        return list(seen.keys())


class _AdaptEmbedding(Embeddings):
    """把 EmbeddingProvider（encode(list[str]) -> list[list[float]]）适配为
    LangChain Embeddings 接口（embed_documents + embed_query）。
    """

    def __init__(self, provider: "EmbeddingProvider"):
        """初始化当前对象的依赖和内部状态。"""
        super().__init__()
        self.provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """执行 embed_documents 逻辑。"""
        return self.provider.encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """执行 embed_query 逻辑。"""
        return self.provider.encode([text])[0]


__all__ = ["SchemaEnsembleRetriever", "SemanticAliasRetriever", "_HAS_VEC"]
