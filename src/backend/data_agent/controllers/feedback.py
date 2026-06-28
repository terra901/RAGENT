"""用户反馈控制器。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..core.config import settings
from ..models.schemas import FeedbackEntryResp, FeedbackRequest
from ..services import AgentRuntime
from .deps import get_runtime

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def get_feedback_store(runtime: AgentRuntime):
    """读取反馈仓储。"""
    store = getattr(runtime, "feedback_store", None)
    if store is None:
        raise HTTPException(status_code=404, detail="反馈功能未启用")
    return store


@router.post("", response_model=FeedbackEntryResp)
async def post_feedback(req: FeedbackRequest, runtime: AgentRuntime = Depends(get_runtime)):
    """创建一条用户反馈。"""
    status_val = "approved" if req.status == "pending" and settings.feedback_auto_approve else req.status
    feedback_store = get_feedback_store(runtime)
    fid = feedback_store.add(req.question, req.sql, status=status_val, note=req.note)
    return FeedbackEntryResp(**feedback_store.get(fid).__dict__)


@router.get("")
async def list_feedback(status: str | None = None, limit: int = 200, runtime: AgentRuntime = Depends(get_runtime)):
    """列出反馈条目。"""
    items = get_feedback_store(runtime).list(status=status, limit=limit)
    return {"items": [FeedbackEntryResp(**item.__dict__) for item in items], "total": len(items)}


@router.post("/{fid}/approve")
async def approve_feedback(fid: int, runtime: AgentRuntime = Depends(get_runtime)):
    """批准一条反馈进入 few-shot。"""
    if not get_feedback_store(runtime).set_status(fid, "approved"):
        raise HTTPException(status_code=404, detail="未找到该反馈")
    return {"status": "approved", "id": fid}


@router.post("/{fid}/reject")
async def reject_feedback(fid: int, runtime: AgentRuntime = Depends(get_runtime)):
    """拒绝一条反馈。"""
    if not get_feedback_store(runtime).set_status(fid, "rejected"):
        raise HTTPException(status_code=404, detail="未找到该反馈")
    return {"status": "rejected", "id": fid}


@router.delete("/{fid}")
async def delete_feedback(fid: int, runtime: AgentRuntime = Depends(get_runtime)):
    """删除一条反馈。"""
    if not get_feedback_store(runtime).delete(fid):
        raise HTTPException(status_code=404, detail="未找到该反馈")
    return {"status": "deleted", "id": fid}
