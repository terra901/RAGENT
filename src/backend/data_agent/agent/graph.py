"""Concise LangGraph definition for the data-query agent."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    execute_sql_node,
    generate_chart_node,
    generate_sql_node,
    interpret_result_node,
    load_memory_node,
    persist_memory_node,
    recall_schema_node,
    validate_sql_node,
)
from .state import AgentState


def route_after_validate(state: AgentState) -> str:
    """Stop on validation error, otherwise execute SQL."""
    return "finish" if state.get("terminated") else "execute_sql"


def route_after_execute(state: AgentState) -> str:
    """Retry SQL generation on DB execution error, or continue to interpretation."""
    if state.get("terminated"):
        return "finish"
    if state.get("retry"):
        return "generate_sql"
    return "interpret_result"


def build_graph():
    """Build the compiled LangGraph workflow.

    Nodes are intentionally small and live in data_agent.agent.nodes.
    """
    builder = StateGraph(AgentState)

    builder.add_node("load_memory", load_memory_node)
    builder.add_node("recall_schema", recall_schema_node)
    builder.add_node("generate_sql", generate_sql_node)
    builder.add_node("validate_sql", validate_sql_node)
    builder.add_node("execute_sql", execute_sql_node)
    builder.add_node("interpret_result", interpret_result_node)
    builder.add_node("generate_chart", generate_chart_node)
    builder.add_node("persist_memory", persist_memory_node)

    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "recall_schema")
    builder.add_edge("recall_schema", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    builder.add_conditional_edges(
        "validate_sql",
        route_after_validate,
        {"execute_sql": "execute_sql", "finish": END},
    )
    builder.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "generate_sql": "generate_sql",
            "interpret_result": "interpret_result",
            "finish": END,
        },
    )
    builder.add_edge("interpret_result", "generate_chart")
    builder.add_edge("generate_chart", "persist_memory")
    builder.add_edge("persist_memory", END)

    return builder.compile()
