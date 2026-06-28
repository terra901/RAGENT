"""AgentRuntime implementation backed by the modular LangGraph workflow."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator

from ..core.logging import get_logger
from ..llm.usage import UsageInfo
from ..memory import MemoryProvider
from ..safety.masking import Masker
from ..services import AgentRuntime, AskResult, RuntimeDependencies, StepInfo, StreamEvent
from ..storage.stores import ResultCacheStore, SessionStore
from .context import RunContext
from .graph import build_graph
from .langfuse import LangfuseObserver
from .state import AgentState
from .utils import dialect_from_url

log = get_logger(__name__)


class GraphQueryRuntime:
    """LangGraph implementation of the AgentRuntime protocol."""

    runtime_name = "graph-query-runtime"
    supports_resume = False

    def __init__(
        self,
        deps: RuntimeDependencies,
    ):
        """Store injected dependencies and prepare runtime helpers."""
        self.connector = deps.connector
        self.schema_manager = deps.schema_manager
        self.llm = deps.llm
        self.result_cache: ResultCacheStore = deps.result_cache
        self.session_store: SessionStore = deps.session_store
        self.feedback_store = deps.feedback_store
        self.sql_template_store = deps.sql_template_store
        self.memory: MemoryProvider = deps.memory_provider
        self.settings = deps.settings
        self.dialect = dialect_from_url(self.settings.db_url)
        sem_layer = getattr(self.schema_manager, "semantic_layer", None)
        sensitive_cols = getattr(sem_layer, "sensitive_columns", {}) if sem_layer else {}
        self.masker = Masker(
            sensitive_columns=sensitive_cols,
            mode=self.settings.masking_mode,
        )
        self._graph = build_graph()
        self._langfuse = LangfuseObserver.from_settings(self.settings)

    async def initialize(self) -> None:
        """Connect to the database and preload schema metadata."""
        await self.connector.connect()
        await self.schema_manager.refresh()
        log.info(
            "Graph runtime ready: dialect=%s tables=%d cache=%s langfuse=%s",
            self.dialect,
            self.schema_manager.table_count(),
            "on" if self.result_cache.enabled else "off",
            "on" if self._langfuse.enabled else "off",
        )

    async def shutdown(self) -> None:
        """Release external resources owned by the runtime."""
        self._langfuse.flush()
        await self.connector.disconnect()

    async def get_history_async(self, session_id: str) -> list[dict[str, str]]:
        """Read stored conversation history."""
        return await self.session_store.get(session_id)

    async def clear_history_async(self, session_id: str) -> None:
        """Clear stored conversation history."""
        await self.session_store.clear(session_id)

    async def ask(self, question: str, session_id: str = "default") -> AskResult:
        """Aggregate the streaming graph execution into one AskResult."""
        steps: list[StepInfo] = []
        final: dict[str, Any] = {}
        rows: list[list[Any]] | None = None
        cols: list[str] | None = None
        row_count = 0
        sql_final: str | None = None
        cache_hit = False
        usage_dict: dict[str, Any] = {}
        error_msg: str | None = None
        thread_id: str | None = None
        chart_spec: dict[str, Any] | None = None

        async for ev in self.ask_stream(question, session_id):
            if ev.type == "step":
                steps.append(StepInfo(**ev.data))
            elif ev.type == "sql":
                sql_final = ev.data.get("sql")
            elif ev.type == "rows":
                cols = ev.data.get("columns")
                rows = ev.data.get("rows")
                row_count = ev.data.get("row_count", 0)
                cache_hit = bool(ev.data.get("cache_hit"))
            elif ev.type == "chart":
                chart_spec = ev.data.get("spec")
            elif ev.type == "usage":
                usage_dict = ev.data
            elif ev.type == "done":
                final = ev.data
                thread_id = ev.data.get("thread_id") or thread_id
                chart_spec = chart_spec or ev.data.get("chart_spec")
            elif ev.type == "error":
                error_msg = ev.data.get("message", "")
                break

        usage = UsageInfo(**usage_dict) if usage_dict else UsageInfo()
        if error_msg:
            return AskResult(
                answer=error_msg,
                sql=sql_final,
                steps=steps,
                total_usage=usage,
                cache_hit=cache_hit,
                memory_used=bool(final.get("memory_used", False)),
                thread_id=thread_id,
            )

        return AskResult(
            answer=final.get("answer", ""),
            sql=sql_final,
            columns=cols,
            rows=rows,
            row_count=row_count,
            execution_time_ms=final.get("execution_time_ms", 0.0),
            visualization_hint=final.get("visualization_hint"),
            chart_spec=chart_spec,
            steps=steps,
            total_usage=usage,
            cache_hit=cache_hit,
            memory_used=final.get("memory_used", False),
            thread_id=thread_id,
        )

    async def ask_stream(self, question: str, session_id: str = "default") -> AsyncIterator[StreamEvent]:
        """Run the graph and yield node-emitted StreamEvents."""
        thread_id = f"{session_id}:{uuid.uuid4().hex[:12]}"
        queue: asyncio.Queue = asyncio.Queue()
        ctx = RunContext(
            runtime=self,
            event_queue=queue,
            thread_id=thread_id,
            session_id=session_id,
            langfuse=self._langfuse,
        )
        state: AgentState = {
            "question": question,
            "session_id": session_id,
            "thread_id": thread_id,
            "attempt": 1,
            "max_attempts": 3,
            "prior_attempts": [],
            "total_usage": UsageInfo(),
            "started_at": time.perf_counter(),
            "terminated": False,
            "retry": False,
        }

        async def run_graph() -> None:
            """Execute graph in the background and signal completion."""
            try:
                with self._langfuse.span(
                    "data_agent.graph",
                    as_type="agent",
                    input={"question": question},
                    metadata={"thread_id": thread_id, "session_id": session_id},
                ):
                    final_state = await self._graph.ainvoke(
                        state,
                        config={"configurable": {"ctx": ctx}, "thread_id": thread_id},
                    )
                    result = final_state.get("result")
                    error = final_state.get("error", "")
                    self._langfuse.update_current(
                        output={
                            "terminated": bool(final_state.get("terminated")),
                            "error": bool(error),
                            "row_count": result.row_count if result is not None else 0,
                            "cache_hit": bool(final_state.get("cache_hit")),
                            "memory_used": bool(final_state.get("memory_used")),
                        },
                        level="ERROR" if error else None,
                        status_message=str(error)[:500] if error else None,
                    )
            except Exception as exc:  # noqa: BLE001
                log.exception("Graph execution failed")
                await queue.put(StreamEvent("error", {"message": f"Agent graph 执行失败: {exc}"}))
            finally:
                self._langfuse.flush()
                await queue.put(None)

        task = asyncio.create_task(run_graph())
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
        await task

    async def ask_resume(self, thread_id: str, user_input: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        """Resume is reserved for a future checkpointer-enabled graph."""
        yield StreamEvent(
            "error",
            {
                "message": "当前 graph runtime 尚未启用可恢复 checkpointer。",
                "thread_id": thread_id,
                "user_input": user_input,
            },
        )


def build_agent_runtime(deps: RuntimeDependencies) -> AgentRuntime:
    """Factory used by DA_AGENT_RUNTIME_FACTORY."""
    return GraphQueryRuntime(deps)
