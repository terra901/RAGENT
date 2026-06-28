"""默认的非图编排问数运行时。"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, AsyncIterator

from langchain_core.language_models import BaseChatModel

from ..connectors.base import BaseConnector
from ..core.config import settings
from ..core.logging import get_logger
from ..memory import MemoryProvider, NullMemoryProvider
from ..query_engine.schema_manager import SchemaManager
from ..safety.masking import Masker
from ..storage.stores import InMemoryResultCache, InMemorySessionStore, ResultCacheStore, SessionStore
from .agent_port import AskResult, StepInfo, StreamEvent
from .query_steps import dialect_from_url
from .query_stream import stream_query

log = get_logger(__name__)


class BasicQueryService:
    """顺序执行的 NL2SQL 运行时，可被 agent graph 适配器替换。"""

    _MAX_EXEC_ATTEMPTS = 3
    runtime_name = "basic-query-service"
    supports_resume = False

    def __init__(
        self,
        connector: BaseConnector,
        schema_manager: SchemaManager,
        llm: BaseChatModel,
        result_cache: ResultCacheStore | None = None,
        session_store: SessionStore | None = None,
        feedback_store: Any | None = None,
        sql_template_store: Any | None = None,
        memory_provider: MemoryProvider | None = None,
    ):
        """注入数据库、LLM、缓存、会话、反馈和记忆依赖。"""
        self.connector = connector
        self.schema_manager = schema_manager
        self.llm = llm
        self._dialect = dialect_from_url(settings.db_url)
        self._sessions = session_store or InMemorySessionStore(
            max_count=settings.session_max_count,
            ttl_seconds=settings.session_ttl_seconds,
        )
        self.result_cache = result_cache or InMemoryResultCache(
            ttl_seconds=settings.result_cache_ttl_seconds,
            max_size=settings.result_cache_max_size,
        )
        self.feedback_store = feedback_store
        self.sql_template_store = sql_template_store
        self.memory = memory_provider or NullMemoryProvider(
            self._sessions,
            recent_n=settings.session_history_turns,
        )
        semantic = getattr(schema_manager, "semantic_layer", None)
        sensitive_cols = getattr(semantic, "sensitive_columns", {}) if semantic else {}
        self.masker = Masker(sensitive_columns=sensitive_cols, mode=settings.masking_mode)

    async def initialize(self) -> None:
        """连接数据库并预加载 Schema 元数据。"""
        await self.connector.connect()
        await self.schema_manager.refresh()
        log.info(
            "运行时已就绪: 名称=%s 方言=%s 表数量=%d 缓存=%s",
            self.runtime_name,
            self._dialect,
            self.schema_manager.table_count(),
            "开启" if self.result_cache.enabled else "关闭",
        )

    async def shutdown(self) -> None:
        """断开数据库连接器。"""
        await self.connector.disconnect()

    async def get_history_async(self, session_id: str) -> list[dict[str, str]]:
        """返回指定会话已存储的历史记录。"""
        return await self._sessions.get(session_id)

    async def clear_history_async(self, session_id: str) -> None:
        """清空指定会话已存储的历史记录。"""
        await self._sessions.clear(session_id)

    async def ask(self, question: str, session_id: str = "default") -> AskResult:
        """消费流式执行路径，并聚合成最终 AskResult。"""
        steps: list[StepInfo] = []
        final: dict[str, Any] = {}
        rows: list[list[Any]] | None = None
        columns: list[str] | None = None
        sql_final: str | None = None
        cache_hit = False
        usage_dict: dict[str, Any] = {}
        error_msg: str | None = None
        chart_spec: dict[str, Any] | None = None

        async for event in self.ask_stream(question, session_id):
            if event.type == "step":
                steps.append(StepInfo(**event.data))
            elif event.type == "sql":
                sql_final = event.data.get("sql")
            elif event.type == "rows":
                columns = event.data.get("columns")
                rows = event.data.get("rows")
                cache_hit = bool(event.data.get("cache_hit"))
            elif event.type == "chart":
                chart_spec = event.data.get("spec")
            elif event.type == "usage":
                usage_dict = event.data
            elif event.type == "done":
                final = event.data
                chart_spec = chart_spec or event.data.get("chart_spec")
            elif event.type == "error":
                error_msg = event.data.get("message", "")
                break

        from ..llm.usage import UsageInfo

        usage = UsageInfo(**usage_dict) if usage_dict else UsageInfo()
        if error_msg:
            return AskResult(answer=error_msg, sql=sql_final, steps=steps, total_usage=usage, cache_hit=cache_hit)
        return AskResult(
            answer=final.get("answer", ""),
            sql=sql_final,
            columns=columns,
            rows=rows,
            row_count=final.get("row_count", 0),
            execution_time_ms=final.get("execution_time_ms", 0.0),
            visualization_hint=final.get("visualization_hint"),
            chart_spec=chart_spec,
            steps=steps,
            total_usage=usage,
            cache_hit=cache_hit,
            memory_used=final.get("memory_used", not isinstance(self.memory, NullMemoryProvider)),
            thread_id=final.get("thread_id"),
        )

    async def ask_stream(self, question: str, session_id: str = "default") -> AsyncIterator[StreamEvent]:
        """顺序运行 NL2SQL 流程，并产出前端可消费事件。"""
        async for event in stream_query(self, question, session_id):
            yield event

    async def ask_resume(self, thread_id: str, user_input: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        """返回错误事件，因为默认运行时不保存可恢复中断状态。"""
        yield StreamEvent(
            "error",
            {
                "message": "当前基础问数运行时不支持恢复执行；请通过 DA_AGENT_RUNTIME_FACTORY 接入 agent 运行时。",
                "thread_id": thread_id,
                "user_input": user_input,
            },
        )
