"""Node: generate SQL from question and schema context."""
from __future__ import annotations

from dataclasses import asdict

from langchain_core.runnables import RunnableConfig

from ...query_engine.nl2sql import NL2SQLChain, StreamChunk
from ..context import emit, get_context
from ..state import AgentState
from ..utils import add_usage, finish_step, start_step, token_note


async def generate_sql_node(state: AgentState, config: RunnableConfig) -> dict:
    """Generate SQL with NL2SQLChain and stream SQL chunks when enabled."""
    ctx = get_context(config)
    attempt = state.get("attempt", 1)
    with ctx.langfuse.span(
        "agent.generate_sql",
        as_type="generation",
        input={"question": state["question"], "attempt": attempt},
        metadata={"thread_id": state["thread_id"], "used_tables": state.get("used_tables", [])},
        model=ctx.runtime.settings.llm_model,
        model_parameters={
            "temperature": ctx.runtime.settings.llm_temperature,
            "max_tokens": ctx.runtime.settings.llm_max_tokens,
        },
    ):
        step_name = "生成 SQL" if attempt == 1 else f"修正 SQL (第{attempt}次)"
        info, started = start_step(step_name, "正在调用 LLM 生成查询...")

        async def on_chunk(chunk: StreamChunk) -> None:
            """Forward SQL token chunks to the frontend stream."""
            if chunk.discard:
                await emit(ctx, "sql_chunk", {"discard": True})
            elif chunk.text:
                await emit(ctx, "sql_chunk", {"text": chunk.text})

        chain = NL2SQLChain(
            llm=ctx.runtime.llm,
            dialect=ctx.runtime.dialect,
            feedback_store=ctx.runtime.feedback_store,
        )
        try:
            result = await chain.generate(
                question=state["question"],
                schema_context=state.get("schema_context", ""),
                conversation_history=state.get("memory_text", ""),
                prior_attempts=state.get("prior_attempts", []),
                chunk_cb=on_chunk if ctx.runtime.settings.stream_llm_tokens else None,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"SQL 生成失败: {exc}"
            ctx.langfuse.update_current(level="ERROR", status_message=message)
            await finish_step(ctx, info, started, detail=message, status="error")
            await emit(ctx, "error", {"message": message})
            return {"terminated": True, "error": message, "retry": False}

        total_usage = add_usage(state.get("total_usage"), result.usage)
        await finish_step(
            ctx,
            info,
            started,
            detail="LLM 已生成 SQL" + token_note(result.usage, result.retries),
        )
        await emit(ctx, "usage", asdict(total_usage))
        if not result.sql:
            message = "无法为此问题生成有效的 SQL 查询，请换种描述。"
            ctx.langfuse.update_current(level="WARNING", status_message=message)
            await emit(ctx, "error", {"message": message})
            return {"terminated": True, "error": message, "total_usage": total_usage, "retry": False}

        await emit(ctx, "sql", {"sql": result.sql, "attempt": attempt})
        ctx.langfuse.update_current(
            output={"sql": result.sql, "retries": result.retries},
            model=ctx.runtime.settings.llm_model,
            model_parameters={
                "temperature": ctx.runtime.settings.llm_temperature,
                "max_tokens": ctx.runtime.settings.llm_max_tokens,
            },
            usage_details=ctx.langfuse.usage_details(result.usage),
        )
        return {
            "sql": result.sql,
            "sql_raw": result.sql_raw,
            "total_usage": total_usage,
            "retry": False,
            "error": "",
        }
