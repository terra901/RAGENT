"""Node: load conversation memory into prompt text."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from ...memory import NullMemoryProvider
from ..context import get_context
from ..state import AgentState
from ..utils import finish_step, start_step


async def load_memory_node(state: AgentState, config: RunnableConfig) -> dict:
    """Load short-term/summary/semantic memory for the current session."""
    ctx = get_context(config)
    with ctx.langfuse.span(
        "agent.load_memory",
        as_type="span",
        input={"session_id": state["session_id"]},
        metadata={"thread_id": state["thread_id"]},
    ):
        info, started = start_step("读取记忆", "正在读取会话上下文...")
        mem_ctx = await ctx.runtime.memory.build(state["session_id"], state["question"])
        memory_text = mem_ctx.to_prompt_text()
        memory_used = not isinstance(ctx.runtime.memory, NullMemoryProvider)
        await finish_step(
            ctx,
            info,
            started,
            detail="已加载上下文" if memory_text else "无可用历史上下文",
        )
        ctx.langfuse.update_current(
            output={"memory_chars": len(memory_text), "memory_used": memory_used}
        )
        return {"memory_text": memory_text, "memory_used": memory_used}
