"""用户反馈存储 + 召回。"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from ..core.config import settings
from ..core.logging import get_logger
from .feedback_bm25 import bm25_recall
from .feedback_models import FEEDBACK_DDL, FeedbackEntry, row_to_entry
from .feedback_vector import build_retriever, build_vector_store, vec_add, vec_delete

log = get_logger(__name__)


class FeedbackStore:
    """自学习 few-shot 的反馈存储。"""

    def __init__(self, db_path: str = "feedback.db", recall_top_k: int = 3, vec_db_path: str | None = None, embedding_provider=None):
        """初始化 SQLite 元数据库和可选向量召回。"""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(FEEDBACK_DDL)
        self.recall_top_k = recall_top_k
        self._vec_db_path = vec_db_path if settings.rag_enabled else None
        self._embedding_provider = embedding_provider
        self._vec = build_vector_store(self._vec_db_path, self._embedding_provider)
        self._retriever = self._build_retriever()
        log.info("FeedbackStore ready at %s (vec=%s)", self._db_path, bool(self._vec))

    def _build_retriever(self):
        """基于当前 approved 反馈重建 retriever。"""
        return build_retriever(self.list(status="approved", limit=10000), self._embedding_provider, self._vec_db_path)

    def _rebuild_retriever(self) -> None:
        """在 approved 列表变化后刷新 retriever。"""
        self._retriever = self._build_retriever()

    def add(self, question: str, sql: str, status: str = "pending", note: str | None = None) -> int:
        """新增反馈样例。"""
        validate_status(status)
        now = time.time()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO feedback(question, sql, status, note, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
                (question, sql, status, note, now, now),
            )
            fid = cur.lastrowid
        if status == "approved":
            self._mirror_status_change(fid, "approved")
        return fid

    def set_status(self, fid: int, status: str, note: str | None = None) -> bool:
        """更新反馈状态。"""
        validate_status(status)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE feedback SET status=?, note=?, updated_at=? WHERE id=?",
                (status, note, time.time(), fid),
            )
        if cur.rowcount > 0:
            self._mirror_status_change(fid, status)
        return cur.rowcount > 0

    def _mirror_status_change(self, fid: int, status: str) -> None:
        """同步 approved 状态到向量库并重建 retriever。"""
        try:
            if status == "approved":
                vec_add(self._vec, self.get(fid))
            else:
                vec_delete(self._vec, fid)
        except Exception as exc:  # noqa: BLE001
            log.warning("FeedbackStore mirror failed (id=%d, status=%s): %s", fid, status, exc)
        self._rebuild_retriever()

    def delete(self, fid: int) -> bool:
        """删除反馈样例。"""
        with self._lock:
            vec_delete(self._vec, fid)
            with self._conn:
                cur = self._conn.execute("DELETE FROM feedback WHERE id=?", (fid,))
                row_count = cur.rowcount
        if row_count > 0:
            self._rebuild_retriever()
        return row_count > 0

    def list(self, status: str | None = None, limit: int = 200) -> list[FeedbackEntry]:
        """列出反馈样例。"""
        sql = "SELECT * FROM feedback"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY id DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(sql, params + (limit,)).fetchall()
        return [row_to_entry(row) for row in rows]

    def get(self, fid: int) -> FeedbackEntry | None:
        """按 ID 读取反馈样例。"""
        with self._lock:
            row = self._conn.execute("SELECT * FROM feedback WHERE id=?", (fid,)).fetchone()
        return row_to_entry(row) if row else None

    def recall(self, question: str) -> list[FeedbackEntry]:
        """对 approved 反馈做召回，优先 ensemble，回落 BM25。"""
        if self._retriever is not None:
            try:
                out = self._retriever.recall(question, self.recall_top_k)
                if out:
                    return out
            except Exception as exc:  # noqa: BLE001
                log.warning("FewShot retriever 失败，回落到 BM25: %s", exc)
        with self._lock:
            rows = self._conn.execute("SELECT * FROM feedback WHERE status='approved'").fetchall()
        return bm25_recall(rows, question, self.recall_top_k)

    def _has_vec_entry(self, fid: int) -> bool:
        """测试辅助：检查 vec 表中是否含某 id。"""
        if self._vec is None:
            return False
        try:
            row = self._vec._connection.execute(
                "SELECT 1 FROM fewshot_vec WHERE json_extract(metadata, '$.id') = ?",
                (fid,),
            ).fetchone()
            return row is not None
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        """关闭 SQLite 连接。"""
        with self._lock:
            self._conn.close()
        if self._vec is not None:
            try:
                self._vec._connection.close()
            except Exception:  # noqa: BLE001
                pass
            self._vec = None


def validate_status(status: str) -> None:
    """校验反馈状态。"""
    if status not in {"pending", "approved", "rejected"}:
        raise ValueError(f"非法 status: {status}")
