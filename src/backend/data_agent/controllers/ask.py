"""问答控制器：同步问答、SSE 流式问答和 resume。"""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.logging import get_logger
from ..models.schemas import AskRequest, AskResponse, ResumeRequest, StepResponse
from ..services import AgentRuntime
from ..storage.auth_store import AuthStore
from .ask_helpers import (
    ask_response_metadata,
    base_stream_metadata,
    llm_configured,
    llm_missing_answer,
    missing_llm_stream,
    persist_user_question,
    sse_format,
    stream_response,
    to_ask_response,
    update_stream_metadata,
)
from .deps import get_auth_store, get_current_user, get_runtime, require_module

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["ask"])


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    req: AskRequest,
    request: Request,
    runtime: AgentRuntime = Depends(get_runtime),
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """运行一次完整问答并返回最终结果。"""
    await require_module(current_user, auth_store, "chat")
    session_id = req.session_id or str(uuid.uuid4())
    user_id = str(current_user["id"])
    await persist_user_question(auth_store, user_id, session_id, req.question)
    if not llm_configured():
        response = AskResponse(answer=llm_missing_answer(), steps=[StepResponse(name="llm_config_check", status="error")])
        await auth_store.append_message(
            conversation_id=session_id,
            user_id=user_id,
            role="assistant",
            content=response.answer,
            metadata={**ask_response_metadata(response), "error": "LLM_API_KEY_MISSING"},
            trace_id=None,
        )
        return response
    tracer = getattr(request.app.state, "tracer", None)
    trace_id = await tracer.start_trace(question=req.question, session_id=session_id) if tracer else ""
    try:
        result = await runtime.ask(req.question, session_id)
        if tracer:
            await tracer.end_trace(status="ok", total_tokens=result.total_usage.total_tokens)
    except Exception as exc:
        log.exception("ask failed: %s", exc)
        if tracer:
            await tracer.end_trace(status="error", error=repr(exc)[:500])
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    response = to_ask_response(result, trace_id or None)
    await auth_store.append_message(
        conversation_id=session_id,
        user_id=user_id,
        role="assistant",
        content=response.answer,
        metadata=ask_response_metadata(response),
        trace_id=response.trace_id,
    )
    return response


@router.post("/ask/stream")
async def ask_stream(
    req: AskRequest,
    request: Request,
    runtime: AgentRuntime = Depends(get_runtime),
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """使用 SSE 流式返回问答过程。"""
    await require_module(current_user, auth_store, "chat")
    session_id = req.session_id or str(uuid.uuid4())
    user_id = str(current_user["id"])
    await persist_user_question(auth_store, user_id, session_id, req.question)
    if not llm_configured():
        return stream_response(missing_llm_stream(auth_store, session_id, user_id))

    async def event_stream() -> AsyncIterator[bytes]:
        trace_id = ""
        status = "ok"
        error_msg: str | None = None
        total_tokens = 0
        answer_parts: list[str] = []
        metadata = base_stream_metadata()
        tracer = getattr(request.app.state, "tracer", None)
        if tracer:
            trace_id = await tracer.start_trace(question=req.question, session_id=session_id)
        try:
            async for event in runtime.ask_stream(req.question, session_id):
                update_stream_metadata(metadata, event.type, event.data, answer_parts, trace_id)
                if event.type == "done":
                    total_tokens = (event.data.get("total_usage") or {}).get("total_tokens", 0)
                elif event.type == "error":
                    status = "error"
                    error_msg = event.data.get("message")
                yield sse_format(event.type, event.data).encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            log.exception("ask_stream failed: %s", exc)
            status = "error"
            error_msg = str(exc)
            yield sse_format("error", {"message": str(exc)}).encode("utf-8")
        finally:
            if tracer:
                await tracer.end_trace(status=status, total_tokens=total_tokens, error=error_msg)
            await persist_assistant_message(auth_store, session_id, user_id, answer_parts, metadata, trace_id, error_msg)

    return stream_response(event_stream())


async def persist_assistant_message(auth_store: AuthStore, session_id: str, user_id: str, answer_parts: list[str], metadata: dict[str, Any], trace_id: str, error_msg: str | None) -> None:
    """把助手回答落库。"""
    content = "".join(answer_parts).strip() or (f"查询失败: {error_msg}" if error_msg else "")
    if not content and not metadata.get("sql") and not error_msg:
        return
    try:
        await auth_store.append_message(
            conversation_id=session_id,
            user_id=user_id,
            role="assistant",
            content=content,
            metadata=metadata,
            trace_id=trace_id or None,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("failed to persist assistant message: %s", exc)


@router.get("/history/{session_id}")
async def get_history(session_id: str, runtime: AgentRuntime = Depends(get_runtime)):
    """返回指定 session 的运行时历史。"""
    return {"session_id": session_id, "history": await runtime.get_history_async(session_id)}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str, runtime: AgentRuntime = Depends(get_runtime)):
    """清空指定 session 的运行时历史。"""
    await runtime.clear_history_async(session_id)
    return {"status": "cleared", "session_id": session_id}


def validate_thread_id_session(thread_id: str, session_id: str) -> bool:
    """确保可恢复线程 ID 属于请求会话。"""
    return bool(thread_id and ":" in thread_id and thread_id.rsplit(":", 1)[0] == session_id)


@router.post("/ask/resume")
async def ask_resume(req: ResumeRequest, runtime: AgentRuntime = Depends(get_runtime)):
    """保留给支持 resume 的运行时使用。"""
    if not validate_thread_id_session(req.thread_id, req.session_id):
        raise HTTPException(status_code=403, detail="thread_id 与 session_id 不匹配")
    if not runtime.supports_resume:
        raise HTTPException(status_code=503, detail="当前运行时未启用 resume")

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for event in runtime.ask_resume(req.thread_id, req.user_input):
                yield sse_format(event.type, event.data).encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            log.exception("resume failed: %s", exc)
            yield sse_format("error", {"message": str(exc)}).encode("utf-8")

    return stream_response(event_stream())
