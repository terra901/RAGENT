"""暴露给 HTTP 层的运行时接口。

API 层只依赖这个协议，不直接依赖具体的 agent 图或节点编排。
后续如需接入 agent 编排，只要实现该协议并配置 `DA_AGENT_RUNTIME_FACTORY`。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from ..llm.usage import UsageInfo


@dataclass
class StepInfo:
    """一次运行步骤的信息，会展示在 HTTP 响应和 SSE 事件中。"""

    name: str
    status: str = "running"
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass
class AskResult:
    """`AgentRuntime.ask()` 返回的聚合问答结果。"""

    answer: str
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    row_count: int = 0
    execution_time_ms: float = 0.0
    visualization_hint: str | None = None
    chart_spec: dict[str, Any] | None = None
    steps: list[StepInfo] = field(default_factory=list)
    total_usage: UsageInfo = field(default_factory=UsageInfo)
    cache_hit: bool = False
    memory_used: bool = False
    trace_id: str | None = None
    thread_id: str | None = None


@dataclass
class StreamEvent:
    """运行时实现向前端发出的一个 SSE 事件。"""

    type: str
    data: dict[str, Any]


@runtime_checkable
class AgentRuntime(Protocol):
    """FastAPI 路由和前端所需的最小运行时接口。"""

    schema_manager: Any
    result_cache: Any
    feedback_store: Any | None
    sql_template_store: Any | None
    supports_resume: bool
    runtime_name: str

    async def initialize(self) -> None:
        """服务开始处理请求前，初始化数据库、缓存等外部资源。"""
        ...

    async def shutdown(self) -> None:
        """应用关闭时释放数据库连接等外部资源。"""
        ...

    async def ask(self, question: str, session_id: str = "default") -> AskResult:
        """执行一次非流式问答请求。"""
        ...

    async def ask_stream(
        self,
        question: str,
        session_id: str = "default",
    ) -> AsyncIterator[StreamEvent]:
        """执行一次流式问答请求，并产出可直接转成 SSE 的事件。"""
        ...

    async def ask_resume(
        self,
        thread_id: str,
        user_input: dict[str, Any],
    ) -> AsyncIterator[StreamEvent]:
        """在运行时支持时，恢复一个被中断的执行线程。"""
        ...

    async def get_history_async(self, session_id: str) -> list[dict[str, str]]:
        """读取指定会话的历史问答记录。"""
        ...

    async def clear_history_async(self, session_id: str) -> None:
        """清空指定会话的历史问答记录。"""
        ...
