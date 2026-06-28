"""Runtime context injected into graph nodes.

Keep non-serializable dependencies here instead of AgentState.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from ..services import StreamEvent
from .langfuse import LangfuseObserver


@dataclass
class RunContext:
    """Per-request dependencies used by graph nodes."""

    runtime: Any
    event_queue: asyncio.Queue
    thread_id: str
    session_id: str
    langfuse: LangfuseObserver


def get_context(config: RunnableConfig) -> RunContext:
    """Read RunContext from LangGraph RunnableConfig."""
    return config["configurable"]["ctx"]


async def emit(ctx: RunContext, event_type: str, data: dict[str, Any]) -> None:
    """Push a StreamEvent into the request event queue."""
    await ctx.event_queue.put(StreamEvent(event_type, data))
