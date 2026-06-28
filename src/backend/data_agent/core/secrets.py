"""敏感凭证加密和脱敏工具。"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def mask_secret(value: str) -> str:
    """生成敏感凭证的脱敏展示值。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return f"{raw[:2]}****"
    return f"{raw[:3]}-****-{raw[-4:]}"


class SecretCipher:
    """基于配置密钥派生 Fernet key 的敏感凭证加解密工具。"""

    def __init__(self, secret: str) -> None:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        """加密敏感凭证。"""
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str | None) -> str:
        """解密敏感凭证；空值或密钥不匹配时返回空字符串。"""
        if not value:
            return ""
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return ""
