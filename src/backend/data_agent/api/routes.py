"""兼容旧导入路径的 API router 聚合。"""
from __future__ import annotations

from fastapi import APIRouter

from ..controllers import admin_models, ask, auth, conversations, feedback, jobs, system, templates, traces

router = APIRouter()
for api_router in (
    auth.router,
    conversations.router,
    system.router,
    ask.router,
    jobs.router,
    templates.router,
    feedback.router,
    traces.router,
    admin_models.router,
):
    router.include_router(api_router)
