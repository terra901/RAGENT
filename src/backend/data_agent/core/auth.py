"""Authentication helpers for RAGENT UI users."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthError(Exception):
    """Authentication validation failure with a stable error code."""

    def __init__(self, message: str = "认证失败", code: str = "AUTH_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_email(value: object) -> str:
    """Normalize and validate a login email address."""
    email = str(value or "").strip().lower()
    if not email:
        raise AuthError("请输入邮箱。", "EMAIL_REQUIRED")
    if not EMAIL_PATTERN.match(email):
        raise AuthError("请输入有效的邮箱地址。", "EMAIL_INVALID")
    return email


def validate_password(password: str) -> None:
    """Validate the registration password policy."""
    if len(password) < 8:
        raise AuthError("密码至少需要 8 个字符。", "PASSWORD_TOO_SHORT")
    if not re.search(r"[A-Za-z]", password):
        raise AuthError("密码需要包含英文字母。", "PASSWORD_NEEDS_LETTER")
    if not re.search(r"\d", password):
        raise AuthError("密码需要包含数字。", "PASSWORD_NEEDS_NUMBER")


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    rounds = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return "pbkdf2_sha256${}${}${}".format(
        rounds,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    """Return whether a plain password matches a stored password hash."""
    try:
        algorithm, rounds_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def generate_token(size: int = 48) -> str:
    """Generate an unpredictable URL-safe token."""
    return secrets.token_urlsafe(size)


def sha256_text(value: str) -> str:
    """Return the SHA256 hex digest of text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sign_jwt(payload: dict[str, Any], secret: str) -> str:
    """Sign a compact HS256 JWT."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64_json(header)
    payload_part = _b64_json(payload)
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64_bytes(signature)}"


def verify_jwt(token: str, secret: str, *, issuer: str) -> dict[str, Any]:
    """Verify JWT signature, issuer and expiry."""
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual = _unb64_bytes(signature_part)
        if not hmac.compare_digest(actual, expected):
            raise AuthError("登录状态已失效。", "TOKEN_INVALID")
        payload = json.loads(_unb64_bytes(payload_part).decode("utf-8"))
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("登录状态已失效。", "TOKEN_INVALID") from exc

    now = int(time.time())
    if payload.get("iss") != issuer:
        raise AuthError("登录状态已失效。", "TOKEN_INVALID")
    if int(payload.get("exp", 0)) <= now:
        raise AuthError("登录已过期。", "TOKEN_EXPIRED")
    return payload


def _b64_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _b64_bytes(raw)


def _b64_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64_bytes(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))
