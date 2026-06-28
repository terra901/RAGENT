"""build_llm() —— 单一入口构造 LangChain ChatOpenAI。"""
from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ..core.config import settings


def build_llm(
    callbacks: list[BaseCallbackHandler] | None = None,
    *,
    model: str | None = None,
) -> BaseChatModel:
    """构造默认 ChatOpenAI，与现有 openai SDK base_url/key/model 兼容。

    Args:
        callbacks: LangChain 回调列表（如 LangChainTracer）。
        model: 覆盖 settings.llm_model 的模型名称。为 None 时使用 settings 值。
    """
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=model or settings.llm_model,
        temperature=0.0,
        streaming=True,
        callbacks=callbacks or [],
    )
