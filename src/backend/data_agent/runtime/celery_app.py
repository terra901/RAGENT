"""Celery 应用配置，使用 RabbitMQ broker。"""
from __future__ import annotations

from celery import Celery

from ..core.config import settings

celery_app = Celery(
    "ragent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend or None,
    include=["data_agent.tasks.ask_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_track_started=True,
    worker_enable_remote_control=False,
)
