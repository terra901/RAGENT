"""从 LangChain AIMessage.usage_metadata 提取 UsageInfo。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UsageInfo:
    """记录一次或多次 LLM 调用的 token 用量。"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_calls: int = 0

    def __add__(self, other: "UsageInfo") -> "UsageInfo":
        """合并两个用量统计对象并返回新对象。"""
        return UsageInfo(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            model_calls=self.model_calls + other.model_calls,
        )


def extract_usage(message: Any) -> UsageInfo:
    """提取 extract_usage 对应的数据。"""
    meta = getattr(message, "usage_metadata", None) or {}
    return UsageInfo(
        prompt_tokens=meta.get("input_tokens", 0) or 0,
        completion_tokens=meta.get("output_tokens", 0) or 0,
        total_tokens=meta.get("total_tokens", 0) or 0,
        model_calls=1,
    )
