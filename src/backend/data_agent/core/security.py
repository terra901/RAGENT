"""安全中间件：API Key 认证 + 简单内存限流。"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from .config import settings
from .logging import get_logger

log = get_logger(__name__)


_PROTECTED_PREFIXES = ("/api/ask", "/api/history")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """如果配置了 settings.api_key，则对受保护路径校验 Authorization Bearer token。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理进入 FastAPI 中间件的单个请求。"""
        expected = settings.api_key
        if expected and request.url.path.startswith(_PROTECTED_PREFIXES):
            header = request.headers.get("authorization", "")
            if not header.lower().startswith("bearer "):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "缺少 Authorization: Bearer 头"},
                )
            token = header.split(" ", 1)[1].strip()
            if token != expected:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "API Key 无效"},
                )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按客户端 IP 做每分钟令牌桶限流（进程内）。"""

    def __init__(self, app, per_minute: int):
        """初始化当前对象的依赖和内部状态。"""
        super().__init__(app)
        self.per_minute = per_minute
        self.window = 60.0
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理进入 FastAPI 中间件的单个请求。"""
        if self.per_minute <= 0 or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path.startswith("/api/health"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self._hits[ip]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()

        if len(bucket) >= self.per_minute:
            retry_after = max(1, int(self.window - (now - bucket[0])))
            log.warning("Rate limit exceeded: ip=%s path=%s", ip, request.url.path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "请求过于频繁，请稍后重试"},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)
