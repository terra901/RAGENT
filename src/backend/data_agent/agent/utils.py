"""Shared helpers for graph nodes and runtime."""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from ..connectors.base import QueryResult
from ..llm.usage import UsageInfo
from ..services import StepInfo
from .context import RunContext, emit


def dialect_from_url(db_url: str) -> str:
    """Infer SQL dialect from SQLAlchemy URL prefix."""
    head = db_url.split(":", 1)[0].lower()
    if head.startswith("mysql"):
        return "mysql"
    if head.startswith("postgres") or head.startswith("postgresql"):
        return "postgres"
    return "sqlite"


def add_usage(current: UsageInfo | None, extra: UsageInfo | None) -> UsageInfo:
    """Add token usage objects while tolerating None."""
    return (current or UsageInfo()) + (extra or UsageInfo())


def token_note(usage: UsageInfo, retries: int = 0) -> str:
    """Format token usage for user-visible step details."""
    retry_note = f" ({retries} 次重试)" if retries else ""
    if not usage.total_tokens:
        return retry_note
    return (
        f"{retry_note} | token 总数: {usage.total_tokens} "
        f"(提示 {usage.prompt_tokens}, 生成 {usage.completion_tokens})"
    )


def start_step(name: str, detail: str = "") -> tuple[StepInfo, float]:
    """Create a running step and timestamp."""
    return StepInfo(name=name, status="running", detail=detail), time.perf_counter()


async def finish_step(
    ctx: RunContext,
    info: StepInfo,
    started_at: float,
    *,
    detail: str | None = None,
    status: str = "done",
) -> None:
    """Emit a completed step event."""
    info.elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    if detail is not None:
        info.detail = detail
    info.status = status
    await emit(ctx, "step", asdict(info))


def rows_payload(result: QueryResult, *, cache_hit: bool, masked_columns: list[str] | None = None) -> dict[str, Any]:
    """Convert QueryResult into the public rows event payload."""
    payload: dict[str, Any] = {
        "columns": result.columns,
        "rows": [list(row) for row in result.rows],
        "row_count": result.row_count,
        "cache_hit": cache_hit,
    }
    if masked_columns:
        payload["masked_columns"] = masked_columns
    return payload


def suggest_visualization(sql: str, result: QueryResult) -> str:
    """Return a lightweight chart hint from SQL/result shape."""
    sql_upper = sql.upper()
    if result.row_count <= 1:
        return "table"
    if any(kw in sql_upper for kw in ("DATE", "MONTH", "YEAR", "STRFTIME", "DATE_TRUNC", "GROUP BY")):
        for col in result.columns:
            if any(t in col.lower() for t in ("date", "time", "month", "year", "day", "季度", "周")):
                return "line"
        numeric_cols = sum(1 for value in result.rows[0] if isinstance(value, (int, float))) if result.rows else 0
        if numeric_cols >= 1:
            return "bar"
    if any(kw in sql_upper for kw in ("RATIO", "PERCENT", "SHARE", "占比", "百分比")):
        return "pie"
    if "ORDER BY" in sql_upper and "DESC" in sql_upper and result.row_count <= 20:
        return "bar"
    return "table"


def fallback_answer(result: QueryResult) -> str:
    """Return a deterministic answer when interpretation fails."""
    return f"查询返回 {result.row_count} 行数据，共 {len(result.columns)} 列。"
