"""Vega-Lite 图表 hint 安全校验。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ALLOWED_MARKS = {"bar", "line", "point", "area", "arc", "rect", "tick", "circle", "square", "text"}
ALLOWED_CHANNELS = {"x", "y", "color", "size", "theta", "radius", "column", "row", "opacity", "tooltip", "shape"}
ALLOWED_TYPES = {"quantitative", "nominal", "ordinal", "temporal"}
ALLOWED_AGGREGATES = {"count", "sum", "mean", "average", "min", "max", "median", "distinct", "valid"}
ALLOWED_SORT = {"ascending", "descending"}
MAX_TITLE_LEN = 80
FIELD_SAFE = re.compile(r"^[A-Za-z_][\w. ]{0,63}$")


@dataclass
class EncodingChannel:
    """单个 Vega-Lite encoding channel。"""

    field: str | None = None
    type: str = "quantitative"
    aggregate: str | None = None
    sort: str | None = None
    title: str | None = None


@dataclass
class ChartHint:
    """LLM 输出的安全图表提示。"""

    mark: str = "bar"
    encoding: dict[str, EncodingChannel] = field(default_factory=dict)
    title: str | None = None


def validate_hint(raw: dict, columns: list[str]) -> ChartHint | None:
    """校验 LLM 输出并构造 ChartHint。"""
    if not isinstance(raw, dict):
        return None
    mark = raw.get("mark")
    if not isinstance(mark, str) or mark not in ALLOWED_MARKS:
        return None
    raw_encoding = raw.get("encoding")
    if not isinstance(raw_encoding, dict) or not raw_encoding:
        return None
    allowed_fields = set(columns)
    cleaned: dict[str, EncodingChannel] = {}
    for name, payload in raw_encoding.items():
        if name not in ALLOWED_CHANNELS:
            continue
        channel = validate_channel(payload, allowed_fields)
        if channel is not None:
            cleaned[name] = channel
    if not cleaned or not any(key in cleaned for key in ("x", "theta", "y")):
        return None
    return ChartHint(mark=mark, encoding=cleaned, title=clean_title(raw.get("title")))


def validate_channel(raw: dict, allowed_fields: set[str]) -> EncodingChannel | None:
    """清洗单个 encoding channel。"""
    if not isinstance(raw, dict):
        return None
    field_name = safe_field_name(raw.get("field", ""), allowed_fields)
    if field_name is None and raw.get("aggregate") not in ALLOWED_AGGREGATES:
        return None
    value_type = raw.get("type", "quantitative")
    if value_type not in ALLOWED_TYPES:
        value_type = "quantitative"
    aggregate = raw.get("aggregate")
    if aggregate is not None and aggregate not in ALLOWED_AGGREGATES:
        aggregate = None
    sort = raw.get("sort")
    if sort is not None and sort not in ALLOWED_SORT:
        sort = None
    return EncodingChannel(field=field_name, type=value_type, aggregate=aggregate, sort=sort, title=clean_title(raw.get("title")))


def safe_field_name(name: str, allowed: set[str]) -> str | None:
    """字段名必须精确匹配查询结果列。"""
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or not FIELD_SAFE.match(name):
        return None
    lower = name.lower()
    for col in allowed:
        if col.lower() == lower:
            return col
    return None


def clean_title(title: Any) -> str | None:
    """去除标题中的控制性字符并限制长度。"""
    if not isinstance(title, str):
        return None
    text = re.sub(r"[<>`]", "", title.strip())
    return text[:MAX_TITLE_LEN] if text else None
