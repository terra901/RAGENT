"""Schema Manager: 表结构发现、缓存与上下文构建（含问题驱动的召回）。

召回策略：
- 表数 <= DA_SCHEMA_RECALL_THRESHOLD 或无 question：全量注入
- 否则按 question 召回 top-K（DA_SCHEMA_RECALL_TOP_K）：BM25 + 语义层别名加权 + 可选 embedding 融合
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.config import settings
from ..connectors.base import BaseConnector, TableInfo
from ..core.logging import get_logger
from ..retrieval.recall import BM25Recaller, EmbeddingProvider, EmbeddingRecaller
from ..retrieval.retriever import SchemaEnsembleRetriever, _HAS_VEC
from .semantic_layer import SemanticLayer

log = get_logger(__name__)


@dataclass
class SchemaManager:
    """封装 SchemaManager 的数据结构或业务行为。"""
    connector: BaseConnector
    semantic_layer: SemanticLayer | None = None
    embedding_provider: EmbeddingProvider | None = None
    _cache: dict[str, TableInfo] = field(default_factory=dict)
    _bm25: BM25Recaller | None = None
    _emb: EmbeddingRecaller | None = None
    _retriever: SchemaEnsembleRetriever | None = field(default=None, repr=False)

    # ---------- 公开 API ----------

    async def refresh(self, *, with_count: bool | None = None) -> None:
        """重新装载所有表结构。

        with_count=None 时使用 settings.schema_with_count。大表 / 锁表场景可
        显式传 False 跳过 COUNT(*)。
        """
        if with_count is None:
            with_count = settings.schema_with_count
        excluded = settings.schema_excluded_table_set()
        tables = [
            table
            for table in await self.connector.get_all_table_info(with_count=with_count)
            if table.name not in excluded
        ]
        self._cache = {t.name: t for t in tables}
        self._rebuild_recallers()
        log.info(
            "Schema refreshed: %d tables (with_count=%s)",
            len(self._cache), with_count,
        )

    async def get_all_tables(self) -> list[str]:
        """获取 all_tables 相关数据。"""
        if not self._cache:
            await self.refresh()
        return list(self._cache.keys())

    async def get_table(self, name: str) -> TableInfo | None:
        """获取 table 相关数据。"""
        if name not in self._cache:
            await self.refresh()
        return self._cache.get(name)

    def table_count(self) -> int:
        """执行 table_count 逻辑。"""
        return len(self._cache)

    def list_all(self) -> list[TableInfo]:
        """返回所有已缓存表的 TableInfo，按表名字典序。供 API 层只读使用。"""
        return [self._cache[name] for name in sorted(self._cache.keys())]

    def build_schema_context(
        self,
        table_names: list[str] | None = None,
        *,
        question: str | None = None,
    ) -> tuple[str, list[str]]:
        """构建 schema_context 对象或数据。"""
        if not self._cache:
            return "-- 数据库中没有已缓存的表结构，请先调用 refresh()", []

        if table_names:
            target = [t for t in table_names if t in self._cache]
        elif question and len(self._cache) > settings.schema_recall_threshold:
            target = self._recall(question)
        else:
            target = list(self._cache.keys())

        parts: list[str] = []
        for name in target:
            info = self._cache.get(name)
            if not info:
                continue
            parts.append(self._render_table(name, info))

        if self.semantic_layer:
            sem_ctx = self.semantic_layer.to_schema_context()
            if sem_ctx:
                parts.append(sem_ctx)

        return "\n\n".join(parts), target

    # ---------- 内部 ----------

    def _rebuild_recallers(self) -> None:
        """执行 rebuild_recallers 逻辑。"""
        extra: dict[str, str] = {}
        if self.semantic_layer:
            # 把语义层别名 / 描述也喂进 BM25 doc
            for m in self.semantic_layer.mappings:
                extra.setdefault(m.table_name, "")
                bits = [m.term, m.description] + list(m.aliases)
                extra[m.table_name] += " " + " ".join(b for b in bits if b)
            for tbl, desc in self.semantic_layer.table_descriptions.items():
                if desc:
                    extra.setdefault(tbl, "")
                    extra[tbl] += " " + desc

        self._bm25 = BM25Recaller()
        self._bm25.fit(self._cache, extra_text_per_table=extra)

        if self.embedding_provider:
            self._emb = EmbeddingRecaller(self.embedding_provider)
            try:
                self._emb.fit(self._cache)
            except Exception as e:  # noqa: BLE001
                log.warning("EmbeddingRecaller.fit 失败，降级到纯 BM25: %s", e)
                self._emb = None
        else:
            self._emb = None

        # ↓↓↓ 新增：构造 LangChain EnsembleRetriever（rag_enabled + [vec] 可用时启用）
        self._retriever = None
        if settings.rag_enabled and _HAS_VEC and self._cache:
            try:
                weights_tuple = settings.rag_fusion_weights_tuple()
                self._retriever = SchemaEnsembleRetriever(
                    schema_cache=self._cache,
                    semantic_layer=self.semantic_layer,
                    embedding_provider=self.embedding_provider,
                    weights=weights_tuple,
                    vec_db_path=settings.vec_db_path,
                    extra_text_per_table=extra,
                )
                log.info("SchemaEnsembleRetriever ready (%d tables, weights=%s)",
                         len(self._cache), weights_tuple)
            except Exception as e:  # noqa: BLE001
                log.warning("SchemaEnsembleRetriever 构造失败，回落到老 _recall: %s", e)
                self._retriever = None

    def _render_table(self, name: str, info: TableInfo) -> str:
        """渲染 render_table 对应的数据片段。"""
        lines = [f"CREATE TABLE {name} ("]
        col_strs = []
        for col in info.columns:
            col_def = f"  {col.name} {col.data_type}"
            if col.is_primary_key:
                col_def += " PRIMARY KEY"
            if not col.nullable:
                col_def += " NOT NULL"
            if col.comment:
                col_def += f"  -- {col.comment}"
            col_strs.append(col_def)
        lines.append(",\n".join(col_strs))
        lines.append(");")
        if info.comment:
            lines.append(f"-- 表说明: {info.comment}")
        if info.row_count is not None:
            lines.append(f"-- 行数: {info.row_count}")
        return "\n".join(lines)

    def _recall(self, question: str) -> list[str]:
        """融合打分：优先 LangChain EnsembleRetriever；否则 BM25 + 语义层硬命中加权 + 可选 embedding。"""
        if self._retriever is not None:
            try:
                picked = self._retriever.recall(question, settings.schema_recall_top_k)
                if picked:
                    log.debug("Schema recall (ensemble) '%s' -> %s", question[:30], picked)
                    return picked
            except Exception as e:  # noqa: BLE001
                log.warning("EnsembleRetriever.recall 失败，回落到老融合: %s", e)

        # === 老路径（fallback；保留原 _recall 逻辑完全一致）===
        # 1) BM25 基线
        bm25_scores = self._bm25.score(question) if self._bm25 else {}
        # 归一化到 [0, 1]
        if bm25_scores:
            mx = max(bm25_scores.values()) or 1.0
            bm25_scores = {k: v / mx for k, v in bm25_scores.items()}

        # 2) 语义层硬命中加 0.5 权
        sem_bonus: dict[str, float] = {}
        if self.semantic_layer:
            for m in self.semantic_layer.find_matches(question):
                sem_bonus[m.table_name] = sem_bonus.get(m.table_name, 0.0) + 0.5

        # 3) embedding（可选），归一化加 0.5 权
        emb_scores: dict[str, float] = {}
        if self._emb:
            try:
                raw = self._emb.score(question)
                mx = max(raw.values(), default=0.0) or 1.0
                emb_scores = {k: 0.5 * v / mx for k, v in raw.items()}
            except Exception as e:  # noqa: BLE001
                log.warning("Embedding score 失败: %s", e)

        # 融合
        all_tables = set(bm25_scores) | set(sem_bonus) | set(emb_scores) | set(self._cache)
        merged = {
            t: bm25_scores.get(t, 0.0) + sem_bonus.get(t, 0.0) + emb_scores.get(t, 0.0)
            for t in all_tables
        }

        top_k = settings.schema_recall_top_k
        ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)
        picked = [n for n, s in ranked if s > 0][:top_k]
        if not picked:
            picked = list(self._cache.keys())[:top_k]
        log.debug("Schema recall (fallback) '%s' -> %s", question[:30], picked)
        return picked
