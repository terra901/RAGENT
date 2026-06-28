"""Node: validate SQL and apply column-level protection."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from ...safety.validator import SafetyValidator
from ..context import emit, get_context
from ..state import AgentState
from ..utils import finish_step, start_step


async def validate_sql_node(state: AgentState, config: RunnableConfig) -> dict:
    """Run safety validation before any SQL reaches the database."""
    ctx = get_context(config)
    with ctx.langfuse.span(
        "agent.validate_sql",
        as_type="guardrail",
        input={"sql": state.get("sql", "")},
        metadata={"thread_id": state["thread_id"]},
    ):
        info, started = start_step("安全校验", "正在检查 SQL 安全性...")
        validator = SafetyValidator(
            max_rows=ctx.runtime.settings.safety_max_rows,
            dialect=ctx.runtime.dialect,
        )
        validation = validator.validate(state.get("sql", ""))
        if not validation.is_valid:
            detail = f"校验失败: {'; '.join(validation.errors)}"
            ctx.langfuse.update_current(level="ERROR", status_message=detail, output={"valid": False})
            await finish_step(ctx, info, started, detail=detail, status="error")
            message = f"SQL 安全校验未通过: {'; '.join(validation.errors)}"
            await emit(ctx, "error", {"message": message})
            return {"terminated": True, "error": message}

        sql = validation.corrected_sql or state.get("sql", "")
        sensitive_hits = ctx.runtime.masker.check_sql_or_raise(sql)
        if sensitive_hits:
            message = f"查询包含敏感列 {sensitive_hits}，已被列级保护拒绝。"
            ctx.langfuse.update_current(
                level="ERROR",
                status_message=message,
                output={"valid": False, "sensitive_columns": sensitive_hits},
            )
            await finish_step(ctx, info, started, detail=message, status="error")
            await emit(ctx, "error", {"message": message, "sensitive_columns": sensitive_hits})
            return {"terminated": True, "error": message}

        if sql != state.get("sql", ""):
            await emit(ctx, "sql", {"sql": sql, "attempt": state.get("attempt", 1), "corrected": True})
            await finish_step(ctx, info, started, detail="已通过校验，自动收紧行数限制")
        else:
            await finish_step(ctx, info, started, detail="已通过校验，查询安全")
        ctx.langfuse.update_current(output={"valid": True})
        return {"sql": sql}
