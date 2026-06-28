"""Celery job 状态 MySQL 仓储。"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..core.config import settings

JOBS_DDL = """
CREATE TABLE IF NOT EXISTS agent_jobs (
  id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  conversation_id CHAR(36) NOT NULL,
  celery_task_id VARCHAR(128) DEFAULT NULL,
  status ENUM('queued','started','success','failed','cancelled') NOT NULL DEFAULT 'queued',
  question MEDIUMTEXT NOT NULL,
  result_json JSON DEFAULT NULL,
  error TEXT DEFAULT NULL,
  queued_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  started_at DATETIME(3) DEFAULT NULL,
  finished_at DATETIME(3) DEFAULT NULL,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_agent_jobs_user_status (user_id, status, queued_at),
  KEY idx_agent_jobs_conversation (conversation_id, queued_at),
  KEY idx_agent_jobs_celery_task (celery_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='RAGENT agent 异步任务队列表'
"""


class AgentJobStore:
    """agent_jobs 表访问层。"""

    def __init__(self, database_url: str | None = None) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url or settings.db_url, echo=False, pool_pre_ping=True)

    async def initialize(self) -> None:
        """创建 job 表。"""
        async with self._engine.begin() as conn:
            await conn.execute(text(JOBS_DDL))

    async def close(self) -> None:
        """释放连接池。"""
        await self._engine.dispose()

    async def create_job(self, *, user_id: str, conversation_id: str, question: str) -> dict[str, Any]:
        """创建 queued 状态任务。"""
        job_id = str(uuid.uuid4())
        async with self._engine.begin() as conn:
            await conn.execute(text(
                """
                INSERT INTO agent_jobs(id, user_id, conversation_id, question)
                VALUES(:id, :user_id, :conversation_id, :question)
                """
            ), {"id": job_id, "user_id": user_id, "conversation_id": conversation_id, "question": question})
        return await self.get_job(job_id) or {}

    async def attach_task(self, job_id: str, task_id: str) -> None:
        """记录 Celery task id。"""
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "UPDATE agent_jobs SET celery_task_id=:task_id WHERE id=:id"
            ), {"id": job_id, "task_id": task_id})

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        """读取单个 job。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text("SELECT * FROM agent_jobs WHERE id=:id LIMIT 1"), {"id": job_id})).mappings().first()
        return dict(row) if row else None

    async def list_user_jobs(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """列出用户最近 job。"""
        limit = max(1, min(int(limit), 100))
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(
                """
                SELECT * FROM agent_jobs
                WHERE user_id=:user_id
                ORDER BY queued_at DESC LIMIT :limit
                """
            ), {"user_id": user_id, "limit": limit})).mappings().all()
        return [dict(row) for row in rows]

    async def queue_snapshot(self, user_id: str) -> dict[str, Any]:
        """返回前端排队提示所需的聚合状态。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(
                """
                SELECT
                  SUM(status='queued') AS queued,
                  SUM(status='started') AS started
                FROM agent_jobs
                WHERE user_id=:user_id AND status IN ('queued','started')
                """
            ), {"user_id": user_id})).mappings().first()
            latest = (await conn.execute(text(
                """
                SELECT id, status, queued_at, started_at
                FROM agent_jobs
                WHERE user_id=:user_id
                ORDER BY queued_at DESC LIMIT 1
                """
            ), {"user_id": user_id})).mappings().first()
        return {"queued": int((row or {}).get("queued") or 0), "started": int((row or {}).get("started") or 0), "latest": dict(latest) if latest else None}
