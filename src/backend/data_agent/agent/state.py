"""Serializable graph state for the data-query agent."""
from __future__ import annotations

from typing import Any, TypedDict

from ..connectors.base import QueryResult
from ..llm.usage import UsageInfo


class AgentState(TypedDict, total=False):
    """State passed between LangGraph nodes.

    Runtime-only objects such as database connectors, queues and clients live in
    RunContext, not here, so the state remains focused on request data.
    """

    question: str
    session_id: str
    thread_id: str
    attempt: int
    max_attempts: int
    terminated: bool
    retry: bool
    error: str

    memory_text: str
    memory_used: bool
    schema_context: str
    used_tables: list[str]
    prior_attempts: list[tuple[str, str]]

    sql: str
    sql_raw: str
    result: QueryResult
    cache_hit: bool
    masked_columns: list[str]

    answer: str
    visualization_hint: str
    chart_spec: dict[str, Any] | None
    total_usage: UsageInfo
    started_at: float
    execution_time_ms: float
