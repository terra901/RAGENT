"""反馈样例向量镜像和 retriever 构建。"""
from __future__ import annotations

from ..core.config import settings
from ..core.logging import get_logger

log = get_logger(__name__)


def build_vector_store(vec_db_path: str | None, embedding_provider):
    """构造 SQLiteVec；依赖缺失时返回 None。"""
    try:
        from ..retrieval.feedback_retriever import _AdaptEmbedding, _HAS_VEC
        if not (vec_db_path and _HAS_VEC and embedding_provider is not None):
            return None
        import sqlite3
        from langchain_community.vectorstores import SQLiteVec
        import sqlite_vec

        conn = sqlite3.connect(vec_db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
        return SQLiteVec(table="fewshot_vec", connection=conn, db_file=vec_db_path, embedding=_AdaptEmbedding(embedding_provider))
    except Exception as exc:  # noqa: BLE001
        log.warning("FeedbackStore vec store init failed: %s", exc)
        return None


def build_retriever(entries, embedding_provider, vec_db_path: str | None):
    """根据 approved 列表构造 ensemble retriever。"""
    try:
        from ..retrieval.feedback_retriever import FewShotEnsembleRetriever, _HAS_VEC
        if not (_HAS_VEC and entries):
            return None
        return FewShotEnsembleRetriever(
            entries=entries,
            embedding_provider=embedding_provider,
            weights=settings.rag_fusion_weights_tuple()[:2] or (0.5, 0.5),
            vec_db_path=vec_db_path,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("FewShot retriever 构造失败: %s", exc)
        return None


def vec_delete(vec, fid: int) -> None:
    """直接从 SQLiteVec 表删除一个样例。"""
    if vec is None:
        return
    try:
        conn = vec._connection
        conn.execute("DELETE FROM fewshot_vec WHERE json_extract(metadata, '$.id') = ?", (fid,))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("Direct vec delete failed (id=%d): %s", fid, exc)


def vec_add(vec, entry) -> None:
    """把 approved 样例写入 SQLiteVec。"""
    if vec is None or entry is None:
        return
    vec.add_texts([entry.question], metadatas=[{"id": entry.id, "sql": entry.sql}], ids=[str(entry.id)])
