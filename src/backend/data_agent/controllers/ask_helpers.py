"""问答控制器 helper。"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, AsyncIterator

from fastapi.responses import StreamingResponse

from ..core.config import settings
from ..models.schemas import AskResponse, StepResponse, UsageResponse
from ..services import AskResult
from ..storage.auth_store import AuthStore
from .conversations import ensure_user_conversation


def llm_configured() -> bool:
    """判断后端是否配置可用 LLM Key。"""
    key = (settings.llm_api_key or "").strip()
    return bool(key and key != "<your-api-key-here>")


def llm_missing_answer() -> str:
    """LLM Key 缺失时的固定回答。"""
    return "当前后端未配置有效的 LLM API Key，聊天记录已保存。配置 DA_LLM_API_KEY 后即可继续执行自然语言问数。"


def ask_response_metadata(response: AskResponse) -> dict[str, Any]:
    """把问答响应转换为消息元数据。"""
    return {
        "sql": response.sql,
        "columns": response.columns,
        "rows": response.rows,
        "row_count": response.row_count,
        "execution_time_ms": response.execution_time_ms,
        "visualization_hint": response.visualization_hint,
        "chart_spec": response.chart_spec,
        "steps": [step.model_dump() for step in response.steps],
        "total_usage": response.total_usage.model_dump(),
        "cache_hit": response.cache_hit,
        "memory_used": response.memory_used,
        "trace_id": response.trace_id,
        "thread_id": response.thread_id,
    }


def to_ask_response(response: AskResult, trace_id: str | None = None) -> AskResponse:
    """把 AskResult 转 API 响应模型。"""
    return AskResponse(
        answer=response.answer,
        sql=response.sql,
        columns=response.columns,
        rows=response.rows,
        row_count=response.row_count,
        execution_time_ms=response.execution_time_ms,
        visualization_hint=response.visualization_hint,
        chart_spec=response.chart_spec,
        steps=[StepResponse(**asdict(step)) for step in response.steps],
        total_usage=UsageResponse(**asdict(response.total_usage)),
        cache_hit=response.cache_hit,
        memory_used=response.memory_used,
        trace_id=trace_id or response.trace_id,
        thread_id=response.thread_id,
    )


def sse_format(event_type: str, data: dict[str, Any]) -> str:
    """按 SSE 格式编码事件。"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


def stream_response(stream: AsyncIterator[bytes]) -> StreamingResponse:
    """创建统一 SSE 响应。"""
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


async def persist_user_question(auth_store: AuthStore, user_id: str, session_id: str, question: str) -> None:
    """确保会话存在并保存用户问题。"""
    await ensure_user_conversation(auth_store=auth_store, user_id=user_id, conversation_id=session_id, question=question)
    await auth_store.append_message(conversation_id=session_id, user_id=user_id, role="user", content=question, metadata={})


async def missing_llm_stream(auth_store: AuthStore, session_id: str, user_id: str) -> AsyncIterator[bytes]:
    """LLM 未配置时返回完整 SSE 响应。"""
    answer = llm_missing_answer()
    step = {"name": "llm_config_check", "status": "error", "detail": "DA_LLM_API_KEY 未配置或仍是占位值"}
    await auth_store.append_message(
        conversation_id=session_id,
        user_id=user_id,
        role="assistant",
        content=answer,
        metadata={"steps": [step], "error": "LLM_API_KEY_MISSING"},
        trace_id=None,
    )
    yield sse_format("step", step).encode("utf-8")
    yield sse_format("answer_chunk", {"text": answer}).encode("utf-8")
    yield sse_format("done", {"answer": answer, "row_count": 0, "trace_id": None}).encode("utf-8")


def base_stream_metadata() -> dict[str, Any]:
    """创建流式问答消息元数据。"""
    return {
        "steps": [],
        "sql": None,
        "columns": None,
        "rows": None,
        "row_count": 0,
        "execution_time_ms": 0,
        "visualization_hint": None,
        "chart_spec": None,
        "total_usage": {},
        "cache_hit": False,
        "trace_id": None,
        "thread_id": None,
    }


def update_stream_metadata(metadata: dict[str, Any], event_type: str, data: dict[str, Any], parts: list[str], trace_id: str) -> None:
    """根据运行时事件更新最终落库元数据。"""
    if event_type == "step":
        idx = next((i for i, item in enumerate(metadata["steps"]) if item.get("name") == data.get("name")), None)
        metadata["steps"].append(dict(data)) if idx is None else metadata["steps"].__setitem__(idx, {**metadata["steps"][idx], **data})
    elif event_type == "sql_chunk" and data.get("text"):
        metadata["sql"] = (metadata.get("sql") or "") + str(data["text"])
    elif event_type == "sql":
        metadata["sql"] = data.get("sql")
    elif event_type == "rows":
        metadata["columns"], metadata["rows"] = data.get("columns"), data.get("rows")
    elif event_type == "answer_chunk" and data.get("text"):
        parts.append(str(data["text"]))
    elif event_type == "chart" and data.get("spec"):
        metadata["chart_spec"] = data["spec"]
    elif event_type == "usage":
        metadata["total_usage"] = dict(data)
    elif event_type == "done":
        merge_done_metadata(metadata, data, parts, trace_id)
    elif event_type == "error":
        metadata["error"] = data.get("message")


def merge_done_metadata(metadata: dict[str, Any], data: dict[str, Any], parts: list[str], trace_id: str) -> None:
    """合并 done 事件字段。"""
    if data.get("answer") and not parts:
        parts.append(str(data["answer"]))
    metadata.update({
        "row_count": data.get("row_count") or 0,
        "execution_time_ms": data.get("execution_time_ms") or 0,
        "visualization_hint": data.get("visualization_hint"),
        "total_usage": data.get("total_usage") or metadata.get("total_usage") or {},
        "cache_hit": bool(data.get("cache_hit")),
        "trace_id": trace_id or None,
        "thread_id": data.get("thread_id"),
    })
    if data.get("chart_spec") and not metadata.get("chart_spec"):
        metadata["chart_spec"] = data["chart_spec"]
