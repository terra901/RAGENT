"""统一日志初始化。"""
from __future__ import annotations

import logging
import sys

from .config import settings


_INITIALIZED = False


def setup_logging() -> None:
    """初始化全局日志处理器和日志级别。"""
    global _INITIALIZED
    if _INITIALIZED:
        return

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """返回已配置好的模块级 logger。"""
    setup_logging()
    return logging.getLogger(name)
