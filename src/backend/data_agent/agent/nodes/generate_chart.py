"""Node: generate optional Vega-Lite chart spec."""
from __future__ import annotations

from dataclasses import asdict

from langchain_core.runnables import RunnableConfig

from ...query_engine.chart_generator import generate_chart_spec
from ..context import emit, get_context
from ..state import AgentState
from ..utils import add_usage, finish_step, start_step, suggest_visualization


async def generate_chart_node(state: AgentState, config: RunnableConfig) -> dict:
    """Generate a chart spec when the result shape is suitable."""
    ctx = get_context(config)
    result = state.get("result")
    if result is None:
        return {}

    viz_hint = suggest_visualization(state.get("sql", ""), result)
    if not ctx.runtime.settings.chart_enabled:
        return {"visualization_hint": viz_hint, "chart_spec": None}

    with ctx.langfuse.span(
        "agent.generate_chart",
        as_type="generation",
        input={"viz_hint": viz_hint},
        metadata={"thread_id": state["thread_id"], "row_count": result.row_count},
        model=ctx.runtime.settings.llm_model,
        model_parameters={
            "temperature": ctx.runtime.settings.llm_temperature,
            "max_tokens": ctx.runtime.settings.llm_max_tokens,
        },
    ):
        info, started = start_step("生成图表", "正在选择 Vega-Lite 图表配置...")
        try:
            chart_spec, chart_usage = await generate_chart_spec(
                ctx.runtime.llm,
                question=state["question"],
                sql=state.get("sql", ""),
                columns=list(result.columns),
                rows=[list(row) for row in result.rows],
                viz_hint=viz_hint,
            )
        except Exception as exc:  # noqa: BLE001
            chart_spec, chart_usage = None, None
            ctx.langfuse.update_current(level="ERROR", status_message=f"图表生成失败: {exc}")
            await finish_step(ctx, info, started, detail=f"图表生成失败，已忽略: {exc}", status="error")
        else:
            if chart_spec is not None:
                await finish_step(ctx, info, started, detail="已生成 Vega-Lite 图表配置")
                await emit(ctx, "chart", {"spec": chart_spec})
            else:
                await finish_step(ctx, info, started, detail="无合适图表，跳过")

        total_usage = add_usage(state.get("total_usage"), chart_usage)
        await emit(ctx, "usage", asdict(total_usage))
        ctx.langfuse.update_current(
            output={"chart": bool(chart_spec)},
            model=ctx.runtime.settings.llm_model,
            model_parameters={
                "temperature": ctx.runtime.settings.llm_temperature,
                "max_tokens": ctx.runtime.settings.llm_max_tokens,
            },
            usage_details=ctx.langfuse.usage_details(chart_usage),
        )
        return {
            "visualization_hint": viz_hint,
            "chart_spec": chart_spec,
            "total_usage": total_usage,
        }
