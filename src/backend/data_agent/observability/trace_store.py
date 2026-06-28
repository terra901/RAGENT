"""Trace 异步 SQLite 存储。

异步 asyncio.Queue + 后台 worker batch flush，不阻塞主流程。
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

from ..core.logging import get_logger
from .models import Span, Trace, TraceSummary

log = get_logger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT,
    question TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    status TEXT,
    total_tokens INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    inputs_json TEXT,
    outputs_json TEXT,
    tokens INTEGER,
    error TEXT,
    FOREIGN KEY(trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, started_at);
CREATE INDEX IF NOT EXISTS idx_traces_started ON traces(started_at DESC);
"""


class TraceStore:
    """封装 TraceStore 的数据结构或业务行为。"""
    def __init__(self, db_path: str, queue_size: int = 1024, flush_interval: float = 0.1, batch_size: int = 32):
        """初始化当前对象的依赖和内部状态。"""
        self._db_path = db_path
        self._queue: asyncio.Queue[tuple[str, object] | None] = asyncio.Queue(maxsize=queue_size)
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._worker_task: asyncio.Task | None = None
        self._stopped = False
        self._dropped_count = 0     # 队列满时丢弃计数
        self._written_count = 0     # 累计成功落盘条数
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def dropped_count(self) -> int:
        """执行 dropped_count 逻辑。"""
        return self._dropped_count

    @property
    def written_count(self) -> int:
        """执行 written_count 逻辑。"""
        return self._written_count

    def _init_schema(self) -> None:
        """执行 init_schema 逻辑。"""
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA foreign_keys = ON")

    async def start(self) -> None:
        """异步执行 start 逻辑。"""
        if self._worker_task is None:
            self._stopped = False
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """异步执行 stop 逻辑。"""
        self._stopped = True
        await self._queue.put(None)  # sentinel
        if self._worker_task is not None:
            with suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

    async def flush(self) -> None:
        """测试用：等待队列清空。"""
        while not self._queue.empty():
            await asyncio.sleep(0.02)
        await asyncio.sleep(self._flush_interval + 0.05)

    async def write_trace(self, t: Trace) -> None:
        """异步执行 write_trace 逻辑。"""
        if self._stopped:
            return
        try:
            self._queue.put_nowait(("trace", t))
        except asyncio.QueueFull:
            self._dropped_count += 1
            log.warning("trace queue full, dropping trace_id=%s (total dropped=%d)",
                        t.trace_id, self._dropped_count)

    async def write_span(self, s: Span) -> None:
        """异步执行 write_span 逻辑。"""
        if self._stopped:
            return
        try:
            self._queue.put_nowait(("span", s))
        except asyncio.QueueFull:
            self._dropped_count += 1
            log.warning("trace queue full, dropping span=%s (total dropped=%d)",
                        s.span_id, self._dropped_count)

    async def update_trace(self, trace_id: str, **fields) -> None:
        """更新 trace 终止字段（ended_at, status, total_tokens, error）。"""
        if self._stopped:
            return
        try:
            self._queue.put_nowait(("update_trace", (trace_id, fields)))
        except asyncio.QueueFull:
            self._dropped_count += 1
            log.warning("trace queue full, dropping update for %s (total dropped=%d)",
                        trace_id, self._dropped_count)

    async def _worker_loop(self) -> None:
        """异步执行 worker_loop 逻辑。"""
        batch: list[tuple[str, object]] = []
        last_flush = time.monotonic()
        while True:
            timeout = max(0.001, self._flush_interval - (time.monotonic() - last_flush))
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                item = None
            if item is None and self._stopped:
                self._do_flush(batch)
                return
            if item is not None:
                batch.append(item)
            if len(batch) >= self._batch_size or (batch and time.monotonic() - last_flush >= self._flush_interval):
                self._do_flush(batch)
                batch = []
                last_flush = time.monotonic()

    def _do_flush(self, batch: list[tuple[str, object]]) -> None:
        """执行 do_flush 逻辑。"""
        if not batch:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                for kind, payload in batch:
                    if kind == "trace":
                        t = payload  # type: ignore[assignment]
                        conn.execute(
                            "INSERT OR REPLACE INTO traces (trace_id, session_id, question, started_at, ended_at, status, total_tokens, error) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            (t.trace_id, t.session_id, t.question, t.started_at, t.ended_at, t.status, t.total_tokens, t.error),
                        )
                    elif kind == "span":
                        s = payload  # type: ignore[assignment]
                        conn.execute(
                            "INSERT OR REPLACE INTO spans (span_id, trace_id, parent_span_id, name, kind, started_at, ended_at, inputs_json, outputs_json, tokens, error) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (s.span_id, s.trace_id, s.parent_span_id, s.name, s.kind, s.started_at, s.ended_at, s.inputs_json, s.outputs_json, s.tokens, s.error),
                        )
                    elif kind == "update_trace":
                        trace_id, fields = payload  # type: ignore[misc]
                        sets = ", ".join(f"{k} = ?" for k in fields)
                        conn.execute(f"UPDATE traces SET {sets} WHERE trace_id = ?", (*fields.values(), trace_id))
                conn.commit()
        except Exception as e:  # noqa: BLE001
            log.error("trace flush failed: %s", e)

    async def get_trace(self, trace_id: str) -> Trace | None:
        """获取 trace 相关数据。"""
        def _q():
            """执行 q 逻辑。"""
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT trace_id, session_id, question, started_at, ended_at, status, total_tokens, error FROM traces WHERE trace_id = ?",
                    (trace_id,),
                ).fetchone()
                if row is None:
                    return None
                return Trace(*row)
        return await asyncio.to_thread(_q)

    async def get_spans(self, trace_id: str) -> list[Span]:
        """获取 spans 相关数据。"""
        def _q():
            """执行 q 逻辑。"""
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT span_id, trace_id, parent_span_id, name, kind, started_at, ended_at, inputs_json, outputs_json, tokens, error FROM spans WHERE trace_id = ? ORDER BY started_at",
                    (trace_id,),
                ).fetchall()
                return [Span(*r) for r in rows]
        return await asyncio.to_thread(_q)

    async def list_traces(self, limit: int = 50, offset: int = 0, session_id: str | None = None) -> list[TraceSummary]:
        """列出 traces 相关数据。"""
        def _q():
            """执行 q 逻辑。"""
            with sqlite3.connect(self._db_path) as conn:
                where = "WHERE t.session_id = ?" if session_id else ""
                args: tuple = (session_id, limit, offset) if session_id else (limit, offset)
                rows = conn.execute(
                    f"""SELECT t.trace_id, t.session_id, t.question, t.started_at, t.status, t.total_tokens,
                              (SELECT COUNT(*) FROM spans s WHERE s.trace_id = t.trace_id) AS span_count,
                              (t.ended_at - t.started_at) * 1000.0 AS duration_ms
                       FROM traces t {where}
                       ORDER BY t.started_at DESC LIMIT ? OFFSET ?""",
                    args,
                ).fetchall()
                return [
                    TraceSummary(
                        trace_id=r[0], session_id=r[1], question=r[2], started_at=r[3],
                        status=r[4] or "running", total_tokens=r[5] or 0, span_count=r[6],
                        duration_ms=r[7] or 0.0,
                    )
                    for r in rows
                ]
        return await asyncio.to_thread(_q)

    async def delete_trace(self, trace_id: str) -> None:
        """删除 trace 相关数据。"""
        def _q():
            """执行 q 逻辑。"""
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("DELETE FROM traces WHERE trace_id = ?", (trace_id,))
                conn.commit()
        await asyncio.to_thread(_q)

    async def cleanup(self, retention_days: int) -> int:
        """异步执行 cleanup 逻辑。"""
        cutoff = time.time() - retention_days * 86400

        def _q():
            """执行 q 逻辑。"""
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                cur = conn.execute("DELETE FROM traces WHERE started_at < ?", (cutoff,))
                conn.commit()
                return cur.rowcount or 0
        return await asyncio.to_thread(_q)
