"""反馈存储数据结构和 SQLite DDL。"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

FEEDBACK_DDL = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    sql TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
"""


@dataclass
class FeedbackEntry:
    """一条用户反馈样例。"""

    id: int
    question: str
    sql: str
    status: str
    note: str | None
    created_at: float
    updated_at: float


def row_to_entry(row: sqlite3.Row) -> FeedbackEntry:
    """SQLite Row 转 FeedbackEntry。"""
    return FeedbackEntry(
        id=row["id"],
        question=row["question"],
        sql=row["sql"],
        status=row["status"],
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
