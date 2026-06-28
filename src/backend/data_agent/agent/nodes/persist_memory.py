"""Node: persist answer into session and memory stores."""
from __future__ import annotations

import time
from dataclasses import asdict

from langchain_core.runnables import RunnableConfig

from ..context import emit, get_context
from ..state import AgentState


async def persist_memory_node(state: AgentState, config: RunnableConfig) -> dict:
    """Persist the final answer and emit the done event."""
    ctx = get_context(config)
    answer = state.get("answer", "")
    with ctx.langfuse.span(
        "agent.persist_memory",
        as_type="span",
        input={"session_id": state["session_id"]},
        metadata={"thread_id": state["thread_id"]},
    ):
        await ctx.runtime.session_store.append(state["session_id"], state["question"], answer)
        await ctx.runtime.memory.on_turn_complete(state["session_id"], state["question"], answer)
        total_ms = round((time.perf_counter() - state.get("started_at", time.perf_counter())) * 1000, 1)
        result = state.get("result")
        await emit(
            ctx,
            "done",
            {
                "answer": answer,
                "execution_time_ms": total_ms,
                "visualization_hint": state.get("visualization_hint"),
                "chart_spec": state.get("chart_spec"),
                "total_usage": asdict(state.get("total_usage")) if state.get("total_usage") else {},
                "cache_hit": bool(state.get("cache_hit")),
                "row_count": result.row_count if result is not None else 0,
                "memory_used": bool(state.get("memory_used")),
                "thread_id": state["thread_id"],
            },
        )
        ctx.langfuse.update_current(output={"done": True, "execution_time_ms": total_ms})
        return {"execution_time_ms": total_ms}
