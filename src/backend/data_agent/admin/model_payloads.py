"""模型管理入参规范化和数据库行转换。"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def normalize_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化供应商入参。"""
    return {
        "name": required(payload, "name", "供应商名称不能为空。"),
        "code": required(payload, "code", "供应商编码不能为空。"),
        "base_url": required(payload, "baseUrl", "Base URL 不能为空。"),
        "api_type": payload.get("apiType") or "openai_compatible",
        "status": to_db_status(str(payload.get("status") or "enabled")),
        "timeout_seconds": int(payload.get("timeoutSeconds") or 60),
        "max_retries": int(payload.get("maxRetries") or 2),
        "remark": str(payload.get("remark") or "").strip(),
    }


def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化模型入参。"""
    data = {
        "display_name": required(payload, "name", "模型名称不能为空。"),
        "model_name": required(payload, "code", "模型型号不能为空。"),
        "model_type": required(payload, "type", "类型不能为空。"),
        "usage_position": required(payload, "usagePosition", "使用位置不能为空。"),
        "api_key": str(payload.get("apiKey") or "").strip(),
        "status": to_db_status(str(payload.get("status") or "enabled")),
        "remark": str(payload.get("remark") or "").strip(),
    }
    if "contextLength" in payload:
        data["context_window"] = nullable_int(payload.get("contextLength"))
    return data


def provider_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """把供应商数据库行转换为前端结构。"""
    return {
        "id": row["id"],
        "name": row["name"],
        "code": row["code"],
        "shortName": str(row["name"] or row["code"])[:2].upper(),
        "baseUrl": row["base_url"],
        "apiType": row["api_type"],
        "authType": "Bearer API Key",
        "status": to_ui_status(row["status"]),
        "timeoutSeconds": row["timeout_seconds"],
        "maxRetries": row["max_retries"],
        "remark": row.get("remark") or "",
        "modelCount": int(row.get("model_count") or 0),
    }


def model_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """把模型数据库行转换为前端结构。"""
    return {
        "id": row["id"],
        "providerId": row["provider_id"],
        "name": row["display_name"],
        "code": row["model_name"],
        "type": row["model_type"],
        "usagePosition": row.get("usage_position") or "",
        "contextLength": str(row.get("context_window") or ""),
        "keyMask": row.get("key_mask") or "",
        "connectivity": row.get("last_test_status") or "unknown",
        "lastTestMessage": row.get("last_test_message") or "",
        "lastTestAt": format_datetime(row.get("last_test_at")),
        "status": to_ui_status(row["status"]),
        "remark": row.get("remark") or "",
    }


def to_ui_status(status: str) -> str:
    """数据库状态转前端状态。"""
    return "enabled" if status == "active" else "disabled"


def to_db_status(status: str) -> str:
    """前端状态转数据库状态。"""
    return "active" if status == "enabled" else "disabled"


def nullable_int(value: Any) -> int | None:
    """把空字符串转换为 NULL。"""
    raw = str(value or "").strip()
    return int(raw) if raw else None


def format_datetime(value: Any) -> str:
    """格式化数据库时间。"""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value or "")


def required(payload: dict[str, Any], key: str, message: str) -> str:
    """读取必填字符串。"""
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(message)
    return value
