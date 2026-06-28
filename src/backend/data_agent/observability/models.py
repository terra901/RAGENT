"""Trace / Span 数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SpanKind = Literal["llm", "chain", "tool", "retrieval", "decision", "sql_exec", "cache"]
TraceStatus = Literal["running", "ok", "error", "terminated"]


@dataclass
class Trace:
    """封装 Trace 的数据结构或业务行为。"""
    trace_id: str
    session_id: str | None
    question: str
    started_at: float
    ended_at: float | None = None
    status: TraceStatus = "running"
    total_tokens: int = 0
    error: str | None = None


@dataclass
class Span:
    """封装 Span 的数据结构或业务行为。"""
    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    kind: SpanKind
    started_at: float
    ended_at: float | None = None
    inputs_json: str | None = None
    outputs_json: str | None = None
    tokens: int | None = None
    error: str | None = None


@dataclass
class TraceSummary:
    """trace 列表项摘要（不含 spans）。"""
    trace_id: str
    question: str
    started_at: float
    status: TraceStatus
    total_tokens: int
    span_count: int
    duration_ms: float
    session_id: str | None = None
