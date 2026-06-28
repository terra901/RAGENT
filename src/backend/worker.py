"""Celery worker 启动入口。

用法：
  celery -A worker.celery_app worker -l info
"""
from __future__ import annotations

from data_agent.runtime.celery_app import celery_app

__all__ = ["celery_app"]
