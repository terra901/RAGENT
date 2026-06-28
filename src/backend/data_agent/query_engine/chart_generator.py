"""Vega-Lite 图表 spec 生成器。

设计原则：
- 后端组装 spec，LLM 只输出 ChartHint（mark + encoding 字段映射）
- 严格白名单校验所有字段（防 prompt injection 把 JS 表达式注入 spec）
- 数据由后端从 QueryResult.rows 构造，不允许 LLM 控制 `data` / `url` / `params`
- 行数 > chart_max_rows 时按等距采样降到上限

输出的 spec 兼容 Vega-Lite v5；前端用 `vega-embed` 就能直接渲染。
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser

from ..core.config import settings
from ..llm.usage import extract_usage
from ..core.logging import get_logger
from ..prompts.chart import CHART_HINT_PROMPT
from .nl2sql import UsageInfo
from .chart_safety import ChartHint, validate_hint

# LangChain 自带 JSON 提取：处理 ```json ... ```、纯 JSON、含解释文本嵌入 JSON 等多种情况
_JSON_PARSER = JsonOutputParser()

log = get_logger(__name__)


# ---------- spec 组装 ----------

def _downsample(rows: list[list[Any]], target: int) -> list[list[Any]]:
    """执行 downsample 逻辑。"""
    if len(rows) <= target or target <= 0:
        return rows
    step = len(rows) / target
    return [rows[int(i * step)] for i in range(target)]


def build_vega_lite_spec(
    hint: ChartHint, columns: list[str], rows: list[list[Any]]
) -> dict | None:
    """把校验过的 ChartHint + 数据组装成 Vega-Lite v5 spec。

    数据完全由后端控制（inline values），不引入外部 URL / data 参数。
    """
    if not hint or not columns:
        return None
    rows = _downsample(list(rows), settings.chart_max_rows)
    values = [dict(zip(columns, row, strict=False)) for row in rows]

    encoding: dict[str, dict] = {}
    for ch_name, ch in hint.encoding.items():
        block: dict[str, Any] = {"type": ch.type}
        if ch.field is not None:
            block["field"] = ch.field
        if ch.aggregate:
            block["aggregate"] = ch.aggregate
        if ch.sort:
            block["sort"] = ch.sort
        if ch.title:
            block["title"] = ch.title
        encoding[ch_name] = block

    spec: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": values},
        "mark": hint.mark,
        "encoding": encoding,
    }
    if hint.title:
        spec["title"] = hint.title
    return spec


# ---------- LLM ----------


def _extract_json(text: str) -> dict | None:
    """LangChain JsonOutputParser 兜底解析。

    保留旧名作为内部 helper：调用方仅在 chart_generator 内使用。返回 dict 或 None。
    JsonOutputParser 处理 ```json ... ``` 包裹、含解释文本嵌入 JSON、纯 JSON 等情况，
    比手写 regex 更鲁棒。
    """
    if not text:
        return None
    try:
        parsed = _JSON_PARSER.parse(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001
        return None


async def generate_chart_hint(
    llm: BaseChatModel,
    *,
    question: str,
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    viz_hint: str | None = None,
    sample_size: int = 8,
) -> tuple[ChartHint | None, UsageInfo]:
    """让 LLM 给出 ChartHint；非法 / 不适合时返回 (None, usage)。"""
    if not columns or not rows:
        return None, UsageInfo()

    sample = rows[:sample_size]
    header = " | ".join(columns)
    rows_text = "\n".join(" | ".join(str(v) for v in row) for row in sample)
    columns_summary = (
        f"列: {header}\n"
        f"样例数据 ({len(sample)} 行):\n{rows_text}\n"
        f"SQL: {sql}\n"
        f"前端预选: {viz_hint or 'unknown'}"
    )

    try:
        chain = CHART_HINT_PROMPT | llm
        msg = await chain.ainvoke({"question": question, "columns_summary": columns_summary})
    except Exception as e:  # noqa: BLE001
        log.warning("图表 LLM 调用失败: %s", e)
        return None, UsageInfo()

    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    usage = extract_usage(msg)

    parsed = _extract_json(text)
    if parsed is None:
        log.debug("图表 LLM 输出无法解析为 JSON: %s", text[:120])
        return None, usage
    # 明确拒绝（mark 为 null）
    if parsed.get("mark") is None:
        return None, usage

    hint = validate_hint(parsed, columns)
    if hint is None:
        log.debug("图表 hint 校验失败: %s", parsed)
    return hint, usage


async def generate_chart_spec(
    llm: BaseChatModel,
    *,
    question: str,
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    viz_hint: str | None = None,
) -> tuple[dict | None, UsageInfo]:
    """端到端：调用 LLM 获取 hint → 校验 → 后端组装 spec。失败返回 None。"""
    if not settings.chart_enabled:
        return None, UsageInfo()
    if len(rows) < settings.chart_min_rows or len(columns) < 2:
        return None, UsageInfo()
    hint, usage = await generate_chart_hint(
        llm,
        question=question, sql=sql,
        columns=columns, rows=rows, viz_hint=viz_hint,
    )
    if hint is None:
        return None, usage
    spec = build_vega_lite_spec(hint, columns, rows)
    return spec, usage
