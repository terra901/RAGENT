"""Embedding Provider 默认实现。

设计原则：
- fastembed 是**可选**依赖（首次启动需下载 ~100MB 模型）。未安装时此模块
  可以正常 import，但实例化 FastEmbedProvider 会抛 RuntimeError，提示用户
  在 requirements.txt 中启用 fastembed 后运行 `pip install -r requirements.txt`。
- 协议定义在 retrieval/recall.py，本文件只放具体实现 + 工厂入口。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..core.logging import get_logger
from .recall import EmbeddingProvider

log = get_logger(__name__)


class FastEmbedProvider:
    """基于 fastembed 的本地 embedding 提供方。

    模型默认 BAAI/bge-small-zh-v1.5（中英混合，~30M 参数，512 维）。
    首次实例化会下载模型；后续启动用本地 cache。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        """初始化当前对象的依赖和内部状态。"""
        try:
            # 延迟导入：未安装 fastembed 时不影响其他模块
            from fastembed import TextEmbedding  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "fastembed 未安装。请在 requirements.txt 中启用 fastembed 后运行 "
                "`pip install -r requirements.txt`，"
                "或在 DA_EMBEDDINGS_ENABLED=false 时关闭本功能。"
            ) from e

        self.model_name = model_name
        log.info("Loading fastembed model: %s", model_name)
        self._model = TextEmbedding(model_name=model_name)
        # warmup 一次，把模型推到 ready 状态
        try:
            _ = list(self._model.embed(["warmup"]))
        except Exception as e:  # noqa: BLE001
            log.warning("fastembed warmup 失败（不致命）: %s", e)

    def encode(self, texts: list[str]) -> list[list[float]]:
        """执行 encode 处理并返回结果。"""
        if not texts:
            return []
        return [list(map(float, v)) for v in self._model.embed(texts)]


@lru_cache(maxsize=1)
def get_default_provider(model_name: str | None = None) -> EmbeddingProvider | None:
    """根据 settings 返回默认 provider 实例（单例）。

    返回 None 表示用户关闭了 embedding 功能（DA_EMBEDDINGS_ENABLED=false）。
    """
    from ..core.config import settings   # 延迟导入避免循环

    if not settings.embeddings_enabled:
        return None

    name = model_name or settings.embeddings_model
    try:
        return FastEmbedProvider(model_name=name)
    except Exception as e:  # noqa: BLE001
        log.error("初始化 FastEmbedProvider 失败，将降级到纯 BM25 召回: %s", e)
        return None


__all__ = ["FastEmbedProvider", "get_default_provider", "EmbeddingProvider"]
