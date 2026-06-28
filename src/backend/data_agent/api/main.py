"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..controllers import admin_models, ask, auth, conversations, feedback, jobs, system, templates, traces
from ..core.config import settings
from ..core.logging import get_logger, setup_logging
from ..core.security import APIKeyMiddleware, RateLimitMiddleware
from .bootstrap import build_app_state, cleanup_app_state

setup_logging()
log = get_logger(__name__)


def _frontend_root() -> Path:
    """返回 FastAPI 挂载的前端目录。"""
    return Path(__file__).resolve().parents[3] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化并释放共享后端依赖。"""
    state = await build_app_state()
    for key, value in state.items():
        setattr(app.state, key, value)
    log.info("Runtime initialized: %s", state["runtime"].runtime_name)
    try:
        yield
    finally:
        await cleanup_app_state(state)
        log.info("Runtime shutdown complete")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    setup_logging()
    app = FastAPI(
        title="RAGENT Data Backend",
        description="Decoupled data-query backend with pluggable agent runtime.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    for router in (auth.router, conversations.router, system.router, ask.router, jobs.router, templates.router, feedback.router, traces.router, admin_models.router):
        app.include_router(router)
    app.mount("/ui", StaticFiles(directory=str(_frontend_root()), html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    async def _root_redirect():
        """把 API 根路径重定向到 UI。"""
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/ui/")

    @app.get("/favicon.ico", include_in_schema=False)
    async def _favicon():
        """把 favicon 请求重定向到前端资源。"""
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/ui/favicon.svg")

    return app


app = create_app()
