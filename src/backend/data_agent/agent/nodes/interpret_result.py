"""Node: interpret SQL result into a natural language answer."""
from __future__ import annotations

from dataclasses import asdict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from ...llm.usage import UsageInfo, extract_usage
from ...prompts.interpret import INTERPRET_RESULT_PROMPT
from ..context import emit, get_context
from ..state import AgentState
from ..utils import add_usage, fallback_answer, finish_step, start_step, token_note


async def interpret_result_node(state: AgentState, config: RunnableConfig) -> dict:
    """Generate a Chinese answer from the SQL result."""
    ctx = get_context(config)
    result = state.get("result")
    if result is None:
        return {"terminated": True, "error": state.get("error", "查询执行失败")}

    with ctx.langfuse.span(
        "agent.interpret_result",
        as_type="generation",
        input={"question": state["question"], "sql": state.get("sql", "")},
        metadata={"thread_id": state["thread_id"], "row_count": result.row_count},
        model=ctx.runtime.settings.llm_model,
        model_parameters={
            "temperature": ctx.runtime.settings.llm_temperature,
            "max_tokens": ctx.runtime.settings.llm_max_tokens,
        },
    ):
        info, started = start_step("解读结果", "正在用 LLM 解读查询结果...")
        if result.row_count == 0:
            answer = "查询结果为空，建议放宽筛选条件或检查数据是否存在。"
            await finish_step(ctx, info, started, detail="结果为空，已生成提示")
            ctx.langfuse.update_current(output={"answer_chars": len(answer), "row_count": 0})
            return {"answer": answer}

        cols = ", ".join(result.columns)
        sample_rows = result.rows[:20]
        rows_preview = "\n".join(" | ".join(str(v) for v in row) for row in sample_rows)
        if result.row_count > 20:
            rows_preview += f"\n... (仅显示前 20 行，共 {result.row_count} 行)"
        inputs = {
            "question": state["question"],
            "sql": state.get("sql", ""),
            "columns": cols,
            "row_count": result.row_count,
            "rows_preview": rows_preview or "(空)",
        }
        chain = INTERPRET_RESULT_PROMPT | ctx.runtime.llm
        answer = ""
        usage = UsageInfo()
        try:
            if ctx.runtime.settings.stream_llm_tokens:
                parts: list[str] = []
                final_msg: AIMessage | None = None
                async for event in chain.astream_events(inputs, version="v2"):
                    kind = event["event"]
                    if kind == "on_chat_model_stream":
                        delta = event["data"]["chunk"]
                        text = delta.content if isinstance(delta.content, str) else ""
                        if text:
                            parts.append(text)
                            await emit(ctx, "answer_chunk", {"text": text})
                    elif kind == "on_chat_model_end":
                        final_msg = event["data"]["output"]
                answer = "".join(parts)
                usage = extract_usage(final_msg) if final_msg else UsageInfo()
            else:
                msg: AIMessage = await chain.ainvoke(inputs)
                answer = msg.content if isinstance(msg.content, str) else str(msg.content)
                usage = extract_usage(msg)
            await finish_step(ctx, info, started, detail="已生成自然语言回答" + token_note(usage))
        except Exception as exc:  # noqa: BLE001
            answer = f"{fallback_answer(result)}(解读失败: {exc})"
            ctx.langfuse.update_current(
                level="ERROR",
                status_message=f"结果解读失败: {exc}",
                output={"fallback": True},
            )
            await finish_step(ctx, info, started, detail=f"解读失败: {exc}", status="error")

        total_usage = add_usage(state.get("total_usage"), usage)
        await emit(ctx, "usage", asdict(total_usage))
        ctx.langfuse.update_current(
            output={"answer_chars": len(answer)},
            model=ctx.runtime.settings.llm_model,
            model_parameters={
                "temperature": ctx.runtime.settings.llm_temperature,
                "max_tokens": ctx.runtime.settings.llm_max_tokens,
            },
            usage_details=ctx.langfuse.usage_details(usage),
        )
        return {"answer": answer, "total_usage": total_usage}
