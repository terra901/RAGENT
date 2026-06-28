"""Node: recall relevant schema and build schema context."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from ..context import get_context
from ..state import AgentState
from ..utils import finish_step, start_step


async def recall_schema_node(state: AgentState, config: RunnableConfig) -> dict:
    """Build schema prompt context for the current question."""
    ctx = get_context(config)
    with ctx.langfuse.span(
        "agent.recall_schema",
        as_type="retriever",
        input={"question": state["question"]},
        metadata={"thread_id": state["thread_id"]},
    ):
        info, started = start_step("检索表结构", "正在召回相关表...")
        schema_context, used_tables = ctx.runtime.schema_manager.build_schema_context(
            question=state["question"]
        )
        await finish_step(
            ctx,
            info,
            started,
            detail=f"已加载 {len(used_tables)}/{ctx.runtime.schema_manager.table_count()} 张表的结构信息",
        )
        ctx.langfuse.update_current(output={"used_tables": used_tables})
        return {"schema_context": schema_context, "used_tables": used_tables}
