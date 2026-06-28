"""RAGENT 身份、权限和聊天历史 MySQL 仓储。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..core.logging import get_logger
from .auth_schema import IDENTITY_CHAT_DDL
from .auth_serializers import message_row_to_dict, naive_utc, normalize_modules, permission_row_to_dict, row_to_dict

log = get_logger(__name__)


class AuthStore:
    """身份和聊天存储，后台使用 MySQL。"""

    def __init__(self, database_url: str):
        self._engine: AsyncEngine = create_async_engine(database_url, echo=False, pool_pre_ping=True)

    async def initialize(self) -> None:
        """创建身份/聊天表并清理过期 refresh session。"""
        async with self._engine.begin() as conn:
            for ddl in IDENTITY_CHAT_DDL:
                await conn.execute(text(ddl))
            await conn.execute(text("DELETE FROM auth_sessions WHERE expires_at <= UTC_TIMESTAMP(3)"))
        log.info("AuthStore ready in MySQL")

    async def close(self) -> None:
        """释放 MySQL engine。"""
        await self._engine.dispose()

    async def create_user(self, *, email: str, password_hash: str, name: str, allowed_modules=None) -> dict[str, Any]:
        """创建一个 active 用户及默认权限。"""
        user_id = str(uuid.uuid4())
        modules_json = json.dumps(normalize_modules(allowed_modules), ensure_ascii=False)
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO users(id,email,password_hash,name,status,is_admin) "
                    "VALUES(:id,:email,:password_hash,:name,'active',0)"
                ), {"id": user_id, "email": email, "password_hash": password_hash, "name": name})
                await conn.execute(text(
                    "INSERT INTO user_permissions(id,user_id,allowed_modules_json) "
                    "VALUES(:id,:user_id,CAST(:modules AS JSON))"
                ), {"id": str(uuid.uuid4()), "user_id": user_id, "modules": modules_json})
        except IntegrityError as exc:
            raise ValueError("EMAIL_EXISTS") from exc
        user = await self.find_user_by_id(user_id)
        if user is None:
            raise RuntimeError("用户创建后读取失败")
        return user

    async def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        """按邮箱查询用户。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text("SELECT * FROM users WHERE email=:email LIMIT 1"), {"email": email})).mappings().first()
        return row_to_dict(row) if row is not None else None

    async def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """按 ID 查询用户。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text("SELECT * FROM users WHERE id=:id LIMIT 1"), {"id": user_id})).mappings().first()
        return row_to_dict(row) if row is not None else None

    async def update_last_login(self, user_id: str) -> None:
        """更新最后登录时间。"""
        async with self._engine.begin() as conn:
            await conn.execute(text("UPDATE users SET last_login_at=UTC_TIMESTAMP(3) WHERE id=:id"), {"id": user_id})

    async def get_permissions(self, user_id: str) -> dict[str, Any] | None:
        """读取用户权限。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text("SELECT * FROM user_permissions WHERE user_id=:user_id LIMIT 1"), {"user_id": user_id})).mappings().first()
        return permission_row_to_dict(row) if row is not None else None

    async def ensure_permissions(self, user_id: str, *, allowed_modules=None) -> dict[str, Any]:
        """为旧用户补默认权限并返回权限。"""
        existing = await self.get_permissions(user_id)
        if existing is not None:
            return existing
        modules_json = json.dumps(normalize_modules(allowed_modules), ensure_ascii=False)
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "INSERT IGNORE INTO user_permissions(id,user_id,allowed_modules_json) "
                "VALUES(:id,:user_id,CAST(:modules AS JSON))"
            ), {"id": str(uuid.uuid4()), "user_id": user_id, "modules": modules_json})
        permissions = await self.get_permissions(user_id)
        if permissions is None:
            raise RuntimeError("用户权限创建后读取失败")
        return permissions

    async def ensure_admin_user(self, *, email: str, password_hash: str, name: str, allowed_modules=None) -> dict[str, Any]:
        """确保启动管理员存在，并授予后台管理权限。"""
        modules_json = json.dumps(normalize_modules(allowed_modules), ensure_ascii=False)
        user_id = str(uuid.uuid4())
        async with self._engine.begin() as conn:
            existing = (await conn.execute(text("SELECT id FROM users WHERE email=:email LIMIT 1"), {"email": email})).mappings().first()
            if existing is None:
                await conn.execute(text(
                    "INSERT INTO users(id,email,password_hash,name,status,is_admin) "
                    "VALUES(:id,:email,:password_hash,:name,'active',1)"
                ), {"id": user_id, "email": email, "password_hash": password_hash, "name": name})
            else:
                user_id = str(existing["id"])
                await conn.execute(text(
                    "UPDATE users SET status='active', is_admin=1, name=:name WHERE id=:id"
                ), {"id": user_id, "name": name})
            await conn.execute(text(
                """
                INSERT INTO user_permissions(
                  id,user_id,can_publish_template,can_manage_users,can_manage_permissions,allowed_modules_json
                ) VALUES(:id,:user_id,1,1,1,CAST(:modules AS JSON))
                ON DUPLICATE KEY UPDATE
                  can_publish_template=1,
                  can_manage_users=1,
                  can_manage_permissions=1,
                  allowed_modules_json=CAST(:modules AS JSON)
                """
            ), {"id": str(uuid.uuid4()), "user_id": user_id, "modules": modules_json})
        user = await self.find_user_by_id(user_id)
        if user is None:
            raise RuntimeError("启动管理员创建后读取失败")
        return user

    async def create_refresh_session(self, *, token_hash: str, user_id: str, ip_address: str, user_agent: str, expires_at: datetime) -> None:
        """保存 refresh session 摘要。"""
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO auth_sessions(token_hash,user_id,ip_address,user_agent,expires_at) "
                "VALUES(:token_hash,:user_id,:ip_address,:user_agent,:expires_at)"
            ), {"token_hash": token_hash, "user_id": user_id, "ip_address": ip_address[:64], "user_agent": user_agent[:512], "expires_at": naive_utc(expires_at)})

    async def get_refresh_session(self, token_hash: str) -> dict[str, Any] | None:
        """读取未过期 refresh session。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT * FROM auth_sessions WHERE token_hash=:token_hash AND expires_at > UTC_TIMESTAMP(3) LIMIT 1"
            ), {"token_hash": token_hash})).mappings().first()
        return row_to_dict(row) if row is not None else None

    async def delete_refresh_session(self, token_hash: str) -> None:
        """删除一个 refresh session。"""
        async with self._engine.begin() as conn:
            await conn.execute(text("DELETE FROM auth_sessions WHERE token_hash=:token_hash"), {"token_hash": token_hash})

    async def delete_refresh_sessions_for_user(self, user_id: str) -> None:
        """删除用户全部 refresh sessions。"""
        async with self._engine.begin() as conn:
            await conn.execute(text("DELETE FROM auth_sessions WHERE user_id=:user_id"), {"user_id": user_id})

    async def create_conversation(self, *, user_id: str, title: str, conversation_id: str | None = None) -> dict[str, Any]:
        """创建聊天会话。"""
        cid = conversation_id or str(uuid.uuid4())
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO chat_conversations(id,user_id,title,last_message_at) VALUES(:id,:user_id,:title,NULL)"
            ), {"id": cid, "user_id": user_id, "title": title[:255] or "新对话"})
        conversation = await self.get_conversation(user_id, cid)
        if conversation is None:
            raise RuntimeError("聊天创建后读取失败")
        return conversation

    async def conversation_id_exists(self, conversation_id: str) -> bool:
        """判断会话 ID 是否已被任何用户占用。"""
        async with self._engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 FROM chat_conversations WHERE id=:id LIMIT 1"), {"id": conversation_id})
            return result.first() is not None

    async def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        """读取用户自己的 active 会话。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(
                """
                SELECT c.*, COUNT(m.id) AS message_count
                FROM chat_conversations c LEFT JOIN chat_messages m ON m.conversation_id = c.id
                WHERE c.user_id=:user_id AND c.id=:id AND c.status='active'
                GROUP BY c.id LIMIT 1
                """
            ), {"user_id": user_id, "id": conversation_id})).mappings().first()
        return row_to_dict(row) if row is not None else None

    async def list_conversations(self, user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """列出用户 active 会话。"""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(
                """
                SELECT c.*, COUNT(m.id) AS message_count
                FROM chat_conversations c LEFT JOIN chat_messages m ON m.conversation_id = c.id
                WHERE c.user_id=:user_id AND c.status='active'
                GROUP BY c.id ORDER BY COALESCE(c.last_message_at, c.updated_at) DESC LIMIT :limit
                """
            ), {"user_id": user_id, "limit": max(1, min(int(limit), 200))})).mappings().all()
        return [row_to_dict(row) for row in rows]

    async def update_conversation_title(self, user_id: str, conversation_id: str, title: str) -> bool:
        """更新会话标题。"""
        return await self._execute_bool(
            "UPDATE chat_conversations SET title=:title WHERE user_id=:user_id AND id=:id AND status='active'",
            {"user_id": user_id, "id": conversation_id, "title": title[:255] or "新对话"},
        )

    async def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """软删除会话。"""
        return await self._execute_bool(
            "UPDATE chat_conversations SET status='deleted' WHERE user_id=:user_id AND id=:id AND status='active'",
            {"user_id": user_id, "id": conversation_id},
        )

    async def _execute_bool(self, sql: str, params: dict[str, Any]) -> bool:
        """执行更新语句并返回是否影响行。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(text(sql), params)
            return bool(result.rowcount)

    async def append_message(self, *, conversation_id: str, user_id: str, role: str, content: str, metadata=None, trace_id: str | None = None) -> dict[str, Any]:
        """追加聊天消息并刷新会话时间。"""
        message_id = str(uuid.uuid4())
        payload = json.dumps(metadata or {}, ensure_ascii=False, default=str)
        async with self._engine.begin() as conn:
            await conn.execute(text(
                """
                INSERT INTO chat_messages(id,conversation_id,user_id,role,content,metadata_json,trace_id)
                VALUES(:id,:conversation_id,:user_id,:role,:content,CAST(:metadata_json AS JSON),:trace_id)
                """
            ), {"id": message_id, "conversation_id": conversation_id, "user_id": user_id, "role": role, "content": content, "metadata_json": payload, "trace_id": trace_id})
            await conn.execute(text(
                "UPDATE chat_conversations SET last_message_at=UTC_TIMESTAMP(3), updated_at=UTC_TIMESTAMP(3) "
                "WHERE id=:id AND user_id=:user_id"
            ), {"id": conversation_id, "user_id": user_id})
        message = await self.get_message(user_id, message_id)
        if message is None:
            raise RuntimeError("消息创建后读取失败")
        return message

    async def get_message(self, user_id: str, message_id: str) -> dict[str, Any] | None:
        """读取用户自己的单条消息。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text("SELECT * FROM chat_messages WHERE id=:id AND user_id=:user_id LIMIT 1"), {"id": message_id, "user_id": user_id})).mappings().first()
        return message_row_to_dict(row) if row is not None else None

    async def list_messages(self, user_id: str, conversation_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """列出 active 会话消息。"""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(
                """
                SELECT m.* FROM chat_messages m
                INNER JOIN chat_conversations c ON c.id = m.conversation_id
                WHERE m.user_id=:user_id AND m.conversation_id=:conversation_id
                  AND c.user_id=:user_id AND c.status='active'
                ORDER BY m.created_at ASC LIMIT :limit
                """
            ), {"user_id": user_id, "conversation_id": conversation_id, "limit": max(1, min(int(limit), 500))})).mappings().all()
        return [message_row_to_dict(row) for row in rows]
