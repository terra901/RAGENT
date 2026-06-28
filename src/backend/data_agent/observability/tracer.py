"""Tracer / span ContextManager + ContextVar 传递。

Tracer 是无状态门面：实际写入由 TraceStore 负责。
"""
from __future__ import annotations

import contextvars
import json
import random
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from ..core.logging import get_logger
from .models import Span, Trace
from .trace_store import TraceStore

log = get_logger(__name__)


current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_trace_id", default="")
current_span_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_span_id", default="")
_current_tracer: contextvars.ContextVar["Tracer | None"] = contextvars.ContextVar("current_tracer", default=None)


def get_current_tracer() -> "Tracer | None":
    """获取 current_tracer 相关数据。"""
    return _current_tracer.get()


def set_current_tracer(t: "Tracer | None") -> None:
    """设置 current_tracer 相关状态。"""
    _current_tracer.set(t)


class _SpanHandle:
    """通过上下文管理器返回，用于 set_output / set_error / 记 tokens。"""
    def __init__(self, span: Span):
        """初始化当前对象的依赖和内部状态。"""
        self._span = span
        self._outputs: dict | None = None
        self._error: str | None = None
        self._tokens: int | None = None

    @property
    def span_id(self) -> str:
        """执行 span_id 逻辑。"""
        return self._span.span_id

    def set_output(self, data: Any) -> None:
        """设置 output 相关状态。"""
        self._outputs = data

    def set_error(self, err: str) -> None:
        """设置 error 相关状态。"""
        self._error = err

    def set_tokens(self, n: int) -> None:
        """设置 tokens 相关状态。"""
        self._tokens = n


class Tracer:
    """封装 Tracer 的数据结构或业务行为。"""
    def __init__(self, store: TraceStore, sample_rate: float = 1.0):
        """初始化当前对象的依赖和内部状态。"""
        self._store = store
        self._sample_rate = sample_rate

    def _sampled(self) -> bool:
        """执行 sampled 逻辑。"""
        return self._sample_rate >= 1.0 or random.random() < self._sample_rate

    async def start_trace(self, question: str, session_id: str | None) -> str:
        """异步执行 start_trace 逻辑。"""
        if not self._sampled():
            return ""
        trace_id = uuid.uuid4().hex
        current_trace_id.set(trace_id)
        await self._store.write_trace(Trace(
            trace_id=trace_id, session_id=session_id,
            question=question[:500], started_at=time.time(),
        ))
        return trace_id

    async def end_trace(self, status: str = "ok", total_tokens: int = 0, error: str | None = None) -> None:
        """异步执行 end_trace 逻辑。"""
        tid = current_trace_id.get()
        if not tid:
            return
        await self._store.update_trace(tid, ended_at=time.time(), status=status,
                                       total_tokens=total_tokens, error=error)

    @asynccontextmanager
    async def span(self, name: str, kind: str, inputs: dict | None = None):
        """异步执行 span 逻辑。"""
        tid = current_trace_id.get()
        if not tid:
            # 未启用 trace，返回空 handle，零写入
            yield _SpanHandle(Span(span_id="", trace_id="", parent_span_id=None,
                                    name=name, kind=kind, started_at=time.time()))
            return
        parent = current_span_id.get() or None
        sp = Span(
            span_id=uuid.uuid4().hex, trace_id=tid, parent_span_id=parent,
            name=name, kind=kind, started_at=time.time(),
            inputs_json=_safe_json(inputs) if inputs is not None else None,
        )
        token = current_span_id.set(sp.span_id)
        handle = _SpanHandle(sp)
        try:
            yield handle
        except Exception as e:  # noqa: BLE001
            handle.set_error(repr(e)[:500])
            raise
        finally:
            sp.ended_at = time.time()
            sp.outputs_json = _safe_json(handle._outputs) if handle._outputs is not None else None
            sp.tokens = handle._tokens
            sp.error = handle._error
            current_span_id.reset(token)
            await self._store.write_span(sp)


def _safe_json(obj: Any, max_bytes: int = 2048) -> str:
    """校验输入安全性并返回可继续使用的值。"""
    try:
        s = json.dumps(obj, ensure_ascii=False, default=lambda x: repr(x)[:200])
    except Exception:  # noqa: BLE001
        s = repr(obj)[:max_bytes]
    if len(s) > max_bytes:
        s = s[:max_bytes] + f"...({len(s) - max_bytes}B truncated)"
    return s


# ---------- LangChain Callback Handler ----------

try:
    from langchain_core.callbacks import BaseCallbackHandler
    _HAS_LANGCHAIN = True
except ImportError:
    BaseCallbackHandler = object  # type: ignore[assignment, misc]
    _HAS_LANGCHAIN = False


class LangChainTracer(BaseCallbackHandler):  # type: ignore[misc]
    """把 LangChain LLM 调用映射成 trace span。

    本类实例可作为 ChatOpenAI / Runnable 的 callback 注入。**run_id** 由 LangChain
    通过 keyword 传入，子类用 **kw 吸收 tags / metadata 等额外字段。
    """

    def __init__(self) -> None:
        """初始化当前对象的依赖和内部状态。"""
        if not _HAS_LANGCHAIN:
            raise RuntimeError("langchain-core 未安装")
        self._run_to_span: dict[str, Span] = {}

    def on_chat_model_start(self, serialized: dict, messages, run_id, parent_run_id=None, **kw) -> None:
        """执行 on_chat_model_start 逻辑。"""
        tracer = get_current_tracer()
        tid = current_trace_id.get()
        if tracer is None or not tid:
            return
        sp = Span(
            span_id=str(run_id), trace_id=tid,
            parent_span_id=current_span_id.get() or None,
            name=(serialized.get("id", ["chat_model"])[-1] if serialized else "chat_model"),
            kind="llm", started_at=time.time(),
            inputs_json=_safe_json({"messages_count": sum(len(m) for m in messages)}),
        )
        self._run_to_span[str(run_id)] = sp

    def on_llm_start(self, serialized: dict, prompts, run_id, parent_run_id=None, **kw) -> None:
        """执行 on_llm_start 逻辑。"""
        self.on_chat_model_start(serialized, [[p] for p in prompts], run_id, parent_run_id)

    def on_llm_end(self, response, run_id, **kw) -> None:
        """执行 on_llm_end 逻辑。"""
        sp = self._run_to_span.pop(str(run_id), None)
        if sp is None:
            return
        sp.ended_at = time.time()
        try:
            usage = (response.llm_output or {}).get("token_usage") or {}
            sp.tokens = usage.get("total_tokens")
        except Exception:  # noqa: BLE001
            pass
        self._enqueue_span(sp)

    def on_llm_error(self, error: Exception, run_id, **kw) -> None:
        """执行 on_llm_error 逻辑。"""
        sp = self._run_to_span.pop(str(run_id), None)
        if sp is None:
            return
        sp.ended_at = time.time()
        sp.error = repr(error)[:500]
        self._enqueue_span(sp)

    @staticmethod
    def _enqueue_span(sp: "Span") -> None:
        """同步 callback 中安全入队 span。

        LangChain callback 既可能从 async 上下文（chain.ainvoke 流水）触发，
        也可能从 worker thread 调用（如 invoke 同步执行某些子任务）。原方案
        `asyncio.create_task(...)` 在无 running loop 时会 RuntimeError；
        且 task 无引用，GC 可能在写库前回收。

        改为直接 put_nowait 到 store 的内部 asyncio.Queue —— put_nowait 本身
        是同步操作，不依赖 running loop；queue 已经存在于 TraceStore 实例。
        失败时退化为 log warning，避免影响 LLM 调用主流程。
        """
        tracer = get_current_tracer()
        if tracer is None:
            return
        store = tracer._store
        if store is None or getattr(store, "_stopped", False):
            return
        try:
            store._queue.put_nowait(("span", sp))
        except Exception:  # noqa: BLE001 — queue full / shutdown / etc.
            store._dropped_count += 1 if hasattr(store, "_dropped_count") else 0
            log.warning("LangChainTracer enqueue dropped span run_id=%s", sp.span_id)
