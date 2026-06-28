"""会话和历史消息控制器。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import ConversationCreateRequest, ConversationUpdateRequest
from ..storage.auth_store import AuthStore
from .deps import get_auth_store, get_current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def title_from_question(question: str) -> str:
    """从第一条问题生成聊天标题。"""
    title = " ".join(str(question or "").strip().split())
    return title[:40] or "新对话"


async def ensure_user_conversation(
    *,
    auth_store: AuthStore,
    user_id: str,
    conversation_id: str,
    question: str,
) -> dict[str, Any]:
    """确保会话属于当前用户，不存在则创建。"""
    conversation = await auth_store.get_conversation(user_id, conversation_id)
    if conversation is not None:
        if str(conversation.get("title") or "") == "新对话":
            title = title_from_question(question)
            await auth_store.update_conversation_title(user_id, conversation_id, title)
            conversation["title"] = title
        return conversation
    if await auth_store.conversation_id_exists(conversation_id):
        raise HTTPException(status_code=403, detail="无权访问该对话")
    return await auth_store.create_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        title=title_from_question(question),
    )


@router.get("")
async def list_conversations(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """列出当前用户的对话。"""
    items = await auth_store.list_conversations(str(current_user["id"]))
    return {"items": items, "total": len(items)}


@router.post("")
async def create_conversation(
    req: ConversationCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """创建一个新对话。"""
    title = (req.title or "新对话").strip() or "新对话"
    item = await auth_store.create_conversation(user_id=str(current_user["id"]), title=title)
    return {"conversation": item}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """返回一个对话及其消息。"""
    conversation = await auth_store.get_conversation(str(current_user["id"]), conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="未找到该对话")
    messages = await auth_store.list_messages(str(current_user["id"]), conversation_id)
    return {"conversation": conversation, "messages": messages}


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    req: ConversationUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """重命名一个对话。"""
    ok = await auth_store.update_conversation_title(str(current_user["id"]), conversation_id, req.title.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该对话")
    return {"conversation": await auth_store.get_conversation(str(current_user["id"]), conversation_id)}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_store: AuthStore = Depends(get_auth_store),
):
    """归档/删除一个对话。"""
    ok = await auth_store.delete_conversation(str(current_user["id"]), conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该对话")
    return {"status": "deleted", "id": conversation_id}
