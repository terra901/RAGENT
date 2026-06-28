"""异步问答任务占位。

HTTP SSE 仍是主路径；该任务用于后台排队和未来长耗时 agent 执行。
"""
from __future__ import annotations

from ..runtime.celery_app import celery_app


@celery_app.task(name="ragent.agent.placeholder")
def placeholder_agent_job(job_id: str) -> dict[str, str]:
    """轻量任务：证明 RabbitMQ/Celery 链路可用。"""
    return {"job_id": job_id, "status": "queued"}
