"""MemoryProvider: conversation memory abstraction for runtime adapters.

接口：
- build(session_id, question) -> MemoryContext
- on_turn_complete(session_id, question, answer) -> None  （同步部分阻塞，异步部分 fire-and-forget）

实现：
- NullMemoryProvider: 仅 window，不做 summary / semantic（fallback）
- CombinedMemoryProvider: Summary + Window + Semantic 三件套（Task 5 实装）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from langchain_core.prompts import ChatPromptTemplate

from ..core.logging import get_logger
from ..observability.decorators import traced

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..storage.stores import SessionStore

log = get_logger(__name__)


@dataclass(frozen=True)
class MemoryTurn:
    """封装 MemoryTurn 的数据结构或业务行为。"""
    question: str
    answer: str
    turn_index: int
    relevance: float


@dataclass(frozen=True)
class MemoryContext:
    """封装 MemoryContext 的数据结构或业务行为。"""
    summary: str | None
    semantic: tuple[MemoryTurn, ...]
    recent: tuple[MemoryTurn, ...]

    def to_prompt_text(self) -> str:
        """执行 to_prompt_text 逻辑。"""
        parts: list[str] = []
        if self.summary:
            parts.append(f"[摘要]\n{self.summary}")
        if self.semantic:
            parts.append("[相关历史轮]")
            parts.extend(f"Q: {t.question}\nA: {t.answer}" for t in self.semantic)
        if self.recent:
            parts.append("[最近对话]")
            parts.extend(f"Q: {t.question}\nA: {t.answer}" for t in self.recent)
        return "\n\n".join(parts)


class MemoryProvider(Protocol):
    """封装 MemoryProvider 的数据结构或业务行为。"""
    async def build(self, session_id: str, question: str) -> MemoryContext:
        """异步执行 build 逻辑。"""
        ...
    async def on_turn_complete(self, session_id: str, question: str, answer: str) -> None:
        """异步执行 on_turn_complete 逻辑。"""
        ...


class NullMemoryProvider:
    """fallback：仅 SessionStore window。"""

    def __init__(self, session_store: SessionStore, recent_n: int):
        """初始化当前对象的依赖和内部状态。"""
        self._sess = session_store
        self._recent_n = recent_n

    async def build(self, session_id: str, question: str) -> MemoryContext:
        """异步执行 build 逻辑。"""
        history = await self._sess.get(session_id)
        recent_raw = history[-self._recent_n :] if self._recent_n > 0 else []
        offset = len(history) - len(recent_raw)
        recent = tuple(
            MemoryTurn(h["question"], h["answer"], offset + i, 0.0) for i, h in enumerate(recent_raw)
        )
        return MemoryContext(summary=None, semantic=(), recent=recent)

    async def on_turn_complete(self, session_id: str, question: str, answer: str) -> None:
        """异步执行 on_turn_complete 逻辑。"""
        return None


# ---------- Summary prompt ----------

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是对话摘要助手。把『旧摘要』和『最新一轮 Q+A』合并为一句简洁中文摘要，"
            "保留关键实体和用户意图。严格控制在 {max_chars} 字以内。只输出摘要本体，不解释。",
        ),
        ("human", "旧摘要：{old}\n\n最新一轮：\nQ: {q}\nA: {a}\n\n请输出新摘要："),
    ]
)


class CombinedMemoryProvider:
    """Summary（异步增量）+ Window（复用 SessionStore）+ Semantic（vec 可选）。"""

    def __init__(
        self,
        *,
        session_store: SessionStore,
        summary_store,
        vec_store,
        summary_llm: BaseChatModel,
        recent_n: int,
        semantic_top_k: int,
        semantic_min_turns: int,
        semantic_threshold: float,
        summary_max_chars: int,
        semantic_overfetch_factor: int = 5,
        semantic_overfetch_min: int = 20,
    ):
        """初始化当前对象的依赖和内部状态。"""
        self._sess = session_store
        self._summary = summary_store
        self._vec = vec_store
        self._llm = summary_llm
        self._recent_n = recent_n
        self._top_k = semantic_top_k
        self._min_turns = semantic_min_turns
        self._threshold = semantic_threshold
        self._max_chars = summary_max_chars
        self._overfetch_factor = semantic_overfetch_factor
        self._overfetch_min = semantic_overfetch_min
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: set[asyncio.Task] = set()

    @traced(kind="memory", name="build", capture_io=False)
    async def build(self, session_id: str, question: str) -> MemoryContext:
        """异步执行 build 逻辑。"""
        history = await self._sess.get(session_id)
        recent_raw = history[-self._recent_n :] if self._recent_n > 0 else []
        offset = len(history) - len(recent_raw)
        recent = tuple(
            MemoryTurn(h["question"], h["answer"], offset + i, 0.0) for i, h in enumerate(recent_raw)
        )
        summary = await self._summary.get(session_id)

        semantic_list: list[MemoryTurn] = []
        if self._vec is not None and len(history) > self._min_turns:
            # SQLiteVec 不支持 metadata filter；过宽召回后在 Python 层按 session_id 过滤
            wider_k = max(self._top_k * self._overfetch_factor, self._overfetch_min)
            try:
                results = await asyncio.to_thread(
                    self._vec.similarity_search_with_score,
                    question,
                    wider_k,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Memory semantic recall failed: %s", e)
                results = []

            for doc, score in results:
                if doc.metadata.get("session_id") != session_id:
                    continue  # 过滤跨 session 噪声
                # SQLiteVec 返回 L2 距离（越小越相关）；距离 > 阈值说明不相关 → 丢弃
                if score is not None and score > self._threshold:
                    continue
                semantic_list.append(
                    MemoryTurn(
                        question=doc.metadata.get("question", ""),
                        answer=doc.metadata.get("answer", ""),
                        turn_index=int(doc.metadata.get("turn_index", -1)),
                        relevance=float(score) if score is not None else 0.0,
                    )
                )
                if len(semantic_list) >= self._top_k:
                    break

        return MemoryContext(summary=summary, semantic=tuple(semantic_list), recent=recent)

    @traced(kind="memory", name="on_turn_complete", capture_io=False)
    async def on_turn_complete(self, session_id: str, question: str, answer: str) -> None:
        # ---- 同步：写 vector（必须完成，否则下一轮召回不到当前轮）----
        """异步执行 on_turn_complete 逻辑。"""
        history = await self._sess.get(session_id)
        turn_index = len(history)
        if self._vec is not None:
            try:
                await asyncio.to_thread(
                    self._vec.add_texts,
                    [f"Q: {question}\nA: {answer}"],
                    [
                        {
                            "session_id": session_id,
                            "turn_index": turn_index,
                            "question": question,
                            "answer": answer,
                        }
                    ],
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Memory vec write failed: %s", e)

        # ---- 异步：增量摘要（fire-and-forget）----
        task = asyncio.create_task(self._update_summary(session_id, question, answer))
        self._pending.add(task)
        task.add_done_callback(self._log_summary_error)

    async def close(self) -> None:
        """关闭记忆后台任务，避免应用退出时继续访问已关闭连接。"""
        tasks = [task for task in self._pending if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_summary(self, session_id: str, question: str, answer: str) -> None:
        """异步执行 update_summary 逻辑。"""
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            old = await self._summary.get(session_id)
            chain = SUMMARY_PROMPT | self._llm
            try:
                resp = await asyncio.wait_for(
                    chain.ainvoke(
                        {
                            "old": old or "（无）",
                            "q": question,
                            "a": answer,
                            "max_chars": self._max_chars,
                        }
                    ),
                    timeout=30.0,
                )
            except TimeoutError:
                log.warning("Summary timeout for session=%s", session_id)
                return
            content = resp.content if hasattr(resp, "content") else str(resp)
            text = str(content).strip()[: self._max_chars]
            if text:
                await self._summary.set(session_id, text)

    def _log_summary_error(self, task: asyncio.Task) -> None:
        """执行 log_summary_error 逻辑。"""
        self._pending.discard(task)
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            log.error("Summary task failed: %s", exc, exc_info=exc)
