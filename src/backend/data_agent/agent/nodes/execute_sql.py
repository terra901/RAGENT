"""Node: execute SQL with result cache and retry signaling."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from ...connectors.base import QueryResult
from ..context import emit, get_context
from ..state import AgentState
from ..utils import finish_step, rows_payload, start_step


async def execute_sql_node(state: AgentState, config: RunnableConfig) -> dict:
    """Execute validated SQL or return a cached result."""
    ctx = get_context(config)
    sql = state.get("sql", "")
    cache_key = ctx.runtime.result_cache.make_key(sql, ctx.runtime.settings.db_url)
    with ctx.langfuse.span(
        "agent.execute_sql",
        as_type="tool",
        input={"cache_key": cache_key},
        metadata={"thread_id": state["thread_id"]},
    ):
        cached = await ctx.runtime.result_cache.get(cache_key)
        info, started = start_step(
            "执行查询",
            "缓存命中，跳过 DB" if cached else "正在数据库中执行查询...",
        )
        if cached is not None:
            result = cached
            await finish_step(ctx, info, started, detail=f"缓存命中: {result.row_count} 行")
            await emit(ctx, "rows", rows_payload(result, cache_hit=True))
            ctx.langfuse.update_current(output={"cache_hit": True, "row_count": result.row_count})
            return {"result": result, "cache_hit": True, "retry": False}

        try:
            result = await ctx.runtime.connector.execute_query(
                sql,
                timeout=ctx.runtime.settings.safety_query_timeout,
            )
            display_rows, masked_cols = ctx.runtime.masker.apply_to_rows(
                list(result.columns),
                [list(row) for row in result.rows],
            )
            if masked_cols:
                result = QueryResult(
                    columns=list(result.columns),
                    rows=display_rows,
                    row_count=result.row_count,
                    execution_time_ms=result.execution_time_ms,
                )
            await ctx.runtime.result_cache.set(cache_key, result)
            await finish_step(
                ctx,
                info,
                started,
                detail=f"返回 {result.row_count} 行，耗时 {result.execution_time_ms}ms",
            )
            await emit(ctx, "rows", rows_payload(result, cache_hit=False, masked_columns=masked_cols))
            ctx.langfuse.update_current(output={"cache_hit": False, "row_count": result.row_count})
            return {
                "result": result,
                "cache_hit": False,
                "masked_columns": masked_cols,
                "retry": False,
            }
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            ctx.langfuse.update_current(
                level="ERROR",
                status_message=f"SQL 执行失败: {err_msg}",
                output={"cache_hit": False, "error": err_msg[:500]},
            )
            prior = list(state.get("prior_attempts", []))
            prior.append((sql, err_msg))
            attempt = state.get("attempt", 1)
            await finish_step(ctx, info, started, detail=f"执行失败: {err_msg}", status="error")
            if attempt >= state.get("max_attempts", 3):
                message = f"查询执行失败（已重试 {attempt} 次）: {err_msg}"
                await emit(ctx, "error", {"message": message})
                return {
                    "terminated": True,
                    "error": message,
                    "prior_attempts": prior,
                    "retry": False,
                }
            return {
                "attempt": attempt + 1,
                "prior_attempts": prior,
                "retry": True,
                "error": err_msg,
            }
