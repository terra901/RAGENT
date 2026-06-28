"""身份与聊天仓储的序列化辅助。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def naive_utc(value: datetime) -> datetime:
    """把 datetime 转成 MySQL DATETIME 友好的 UTC naive 值。"""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    """把 SQLAlchemy RowMapping 转为可 JSON 化 dict。"""
    data = dict(row)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = value.isoformat(timespec="milliseconds") + "Z"
    return data


def message_row_to_dict(row: Any) -> dict[str, Any]:
    """转换聊天消息行并解析 metadata_json。"""
    data = row_to_dict(row)
    metadata = data.pop("metadata_json", {}) or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    data["metadata"] = metadata if isinstance(metadata, dict) else {}
    return data


def normalize_modules(value: list[str] | tuple[str, ...] | None) -> list[str]:
    """去重并清理 allowed_modules。"""
    modules = []
    for item in value or []:
        module = str(item).strip()
        if module and module not in modules:
            modules.append(module)
    return modules


def permission_row_to_dict(row: Any) -> dict[str, Any]:
    """转换权限记录为公开结构。"""
    data = row_to_dict(row)
    modules_raw = data.get("allowed_modules_json") or []
    if isinstance(modules_raw, str):
        try:
            modules_raw = json.loads(modules_raw)
        except json.JSONDecodeError:
            modules_raw = []
    modules = modules_raw if isinstance(modules_raw, list) else []
    return {
        "can_create_template": bool(data.get("can_create_template")),
        "can_update_own_template": bool(data.get("can_update_own_template")),
        "can_delete_own_template": bool(data.get("can_delete_own_template")),
        "can_view_public_template": bool(data.get("can_view_public_template")),
        "can_publish_template": bool(data.get("can_publish_template")),
        "can_import_template": bool(data.get("can_import_template")),
        "can_export_template": bool(data.get("can_export_template")),
        "can_manage_users": bool(data.get("can_manage_users")),
        "can_manage_permissions": bool(data.get("can_manage_permissions")),
        "allowed_modules": normalize_modules([str(item) for item in modules]),
    }
