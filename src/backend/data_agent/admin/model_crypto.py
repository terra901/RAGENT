"""模型密钥加密与脱敏。"""
from __future__ import annotations

from ..core.secrets import SecretCipher, mask_secret


def mask_api_key(value: str) -> str:
    """生成 API Key 脱敏展示值。"""
    return mask_secret(value)


class ModelKeyCipher(SecretCipher):
    """模型 API Key 加解密工具。"""

