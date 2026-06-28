"""异步任务和排队状态控制器。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models.schemas import AskRequest
from ..runtime.celery_app import celery_app
from ..runtime.job_store import AgentJobStore
from ..storage.auth_store import AuthStore
from .conversations import ensure_user_conversation
from .deps import get_auth_store, get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_job_store(request: Request) -> AgentJobStore:
    """从应用状态读取 job 仓储。"""
    store = getattr(request.app.state, "job_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="任务队列未初始化")
    return store


@router.get("/queue")
async def queue_status(
    current_user: dict[str, Any] = Depends(get_current_user),
    job_store: AgentJobStore = Depends(get_job_store),
):
    """返回当前用户排队状态。"""
    return await job_store.queue_snapshot(str(current_user["id"]))


@router.get("")
async def list_jobs(
    limit: int = 20,
    current_user: dict[str, Any] = Depends(get_current_user),
    job_store: AgentJobStore = Depends(get_job_store),
):
    """列出当前用户最近异步任务。"""
    items = await job_store.list_user_jobs(str(current_user["id"]), limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/ask")
async def enqueue_ask(
    req: AskRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
    job_store: AgentJobStore = Depends(get_job_store),
):
    """创建一个异步问答任务并投递到 RabbitMQ。"""
    user_id = str(current_user["id"])
    conversation_id = req.session_id
    await ensure_user_conversation(
        auth_store=auth_store,
        user_id=user_id,
        conversation_id=conversation_id,
        question=req.question,
    )
    job = await job_store.create_job(user_id=user_id, conversation_id=conversation_id, question=req.question)
    task = celery_app.send_task("ragent.agent.placeholder", args=[job["id"]])
    await job_store.attach_task(job["id"], task.id)
    job["celery_task_id"] = task.id
    return {"job": job}
