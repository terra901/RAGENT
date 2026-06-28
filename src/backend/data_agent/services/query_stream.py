"""问数流式执行流程。"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator

from ..connectors.base import QueryResult
from ..core.config import settings
from ..llm.usage import UsageInfo
from ..memory import NullMemoryProvider
from ..query_engine.nl2sql import StreamChunk
from ..safety.validator import SafetyValidator
from .agent_port import StreamEvent
from .query_steps import (
    analyze_intent,
    finish_step,
    generate_chart,
    interpret_result,
    make_nl2sql_chain,
    start_step,
    suggest_visualization,
    token_note,
)


async def stream_query(service, question: str, session_id: str) -> AsyncIterator[StreamEvent]:
    """执行完整 NL2SQL 流程并持续产出事件。"""
    thread_id = f"{session_id}:{uuid.uuid4().hex[:12]}"
    memory_context = await service.memory.build(session_id, question)
    history_text = memory_context.to_prompt_text()
    total_usage = UsageInfo()
    started_at = time.perf_counter()

    yield from_step("理解问题", analyze_intent(question))
    schema_context, used_tables = service.schema_manager.build_schema_context(question=question)
    yield finish_schema_step(len(used_tables), service.schema_manager.table_count())

    validator = SafetyValidator(max_rows=settings.safety_max_rows, dialect=service._dialect)
    prior_attempts: list[tuple[str, str]] = []
    sql = ""
    result: QueryResult | None = None
    cache_hit = False

    async for event, payload in _generate_and_execute(service, question, history_text, schema_context, prior_attempts, validator):
        if event == "usage":
            total_usage = total_usage + payload
            yield StreamEvent("usage", asdict(total_usage))
        elif event == "result":
            sql, result, cache_hit = payload
        else:
            yield payload
        if event == "stop":
            return
    if result is None:
        yield StreamEvent("error", {"message": "查询执行失败"})
        return

    result = _masked_result(service, sql, result)
    yield StreamEvent("rows", {"columns": result.columns, "rows": [list(r) for r in result.rows], "row_count": result.row_count, "cache_hit": cache_hit})

    answer, total_usage = await _interpret(service, question, sql, result, total_usage)
    async for event in _chart_events(service, question, sql, result, total_usage):
        if event.type == "usage":
            total_usage = UsageInfo(**event.data)
        yield event

    await service._sessions.append(session_id, question, answer)
    await service.memory.on_turn_complete(session_id, question, answer)
    yield StreamEvent("done", {
        "answer": answer,
        "execution_time_ms": round((time.perf_counter() - started_at) * 1000, 1),
        "visualization_hint": suggest_visualization(sql, result),
        "total_usage": asdict(total_usage),
        "cache_hit": cache_hit,
        "row_count": result.row_count,
        "memory_used": not isinstance(service.memory, NullMemoryProvider),
        "thread_id": thread_id,
    })


def from_step(name: str, keywords: list[str]) -> StreamEvent:
    """生成问题理解步骤事件。"""
    info, started = start_step(name, "正在分析问题意图...")
    detail = f"识别到关键词: {', '.join(keywords[:5])}" if keywords else "通用查询"
    return finish_step(info, started, detail=detail)


def finish_schema_step(used_count: int, table_count: int) -> StreamEvent:
    """生成 Schema 检索步骤事件。"""
    info, started = start_step("检索表结构", "正在召回相关表...")
    return finish_step(info, started, detail=f"已加载 {used_count}/{table_count} 张表的结构信息")


async def _generate_and_execute(service, question: str, history_text: str, schema_context: str, prior_attempts, validator):
    """生成 SQL、校验并执行查询。"""
    for attempt in range(1, service._MAX_EXEC_ATTEMPTS + 1):
        async for event in _generate_sql(service, question, history_text, schema_context, prior_attempts, attempt):
            if event.type == "usage":
                yield "usage", UsageInfo(**event.data)
            else:
                yield "event", event
            if event.type == "error":
                yield "stop", event
                return
        sql = getattr(service, "_last_sql", "")
        yield "event", StreamEvent("sql", {"sql": sql, "attempt": attempt})
        validation_event = _validate_sql(service, validator, sql)
        yield "event", validation_event
        if validation_event.data.get("status") == "error":
            yield "stop", StreamEvent("error", {"message": validation_event.data.get("detail")})
            return
        result_event = await _execute_sql(service, sql)
        yield "event", result_event["step"]
        if result_event.get("result") is not None:
            yield "result", (sql, result_event["result"], bool(result_event.get("cache_hit")))
            return
        prior_attempts.append((sql, result_event["error"]))
        if attempt >= service._MAX_EXEC_ATTEMPTS:
            yield "stop", StreamEvent("error", {"message": f"查询执行失败（已重试 {attempt} 次）: {result_event['error']}"})


async def _generate_sql(service, question: str, history_text: str, schema_context: str, prior_attempts, attempt: int):
    """调用 LLM 生成 SQL，并按配置流式输出 SQL token。"""
    step_name = "生成 SQL" if attempt == 1 else f"修正 SQL (第{attempt}次)"
    info, started = start_step(step_name, "正在调用 LLM 生成查询...")
    queue: asyncio.Queue | None = asyncio.Queue() if settings.stream_llm_tokens else None

    async def on_chunk(chunk: StreamChunk):
        if queue is not None:
            await queue.put(chunk)

    async def run_chain():
        return await make_nl2sql_chain(service).generate(
            question=question,
            schema_context=schema_context,
            conversation_history=history_text,
            prior_attempts=prior_attempts,
            chunk_cb=on_chunk if queue is not None else None,
        )

    try:
        if queue is None:
            result = await run_chain()
        else:
            result = await _drain_sql_queue(run_chain, queue)
    except Exception as exc:  # noqa: BLE001
        yield finish_step(info, started, detail=f"LLM 调用失败: {exc}", status="error")
        yield StreamEvent("error", {"message": f"SQL 生成失败: {exc}"})
        return
    service._last_sql = result.sql
    yield finish_step(info, started, detail="LLM 已生成 SQL" + token_note(result.usage, result.retries))
    yield StreamEvent("usage", asdict(result.usage))
    if not result.sql:
        yield StreamEvent("error", {"message": "无法为此问题生成有效的 SQL 查询，请换种描述。"})


async def _drain_sql_queue(runner, queue: asyncio.Queue):
    """消费 SQL token 队列并等待后台生成完成。"""
    task = asyncio.create_task(runner())
    while not task.done():
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            continue
        if isinstance(item, StreamChunk):
            continue
    return await task


def _validate_sql(service, validator: SafetyValidator, sql: str) -> StreamEvent:
    """执行 SQL 安全校验。"""
    info, started = start_step("安全校验", "正在检查 SQL 安全性...")
    validation = validator.validate(sql)
    if not validation.is_valid:
        return finish_step(info, started, detail=f"SQL 安全校验未通过: {'; '.join(validation.errors)}", status="error")
    sensitive_hits = service.masker.check_sql_or_raise(validation.corrected_sql or sql)
    if sensitive_hits:
        return finish_step(info, started, detail=f"查询包含敏感列 {sensitive_hits}", status="error")
    if validation.corrected_sql and validation.corrected_sql != sql:
        service._last_sql = validation.corrected_sql
        return finish_step(info, started, detail="已通过校验，自动收紧行数限制")
    return finish_step(info, started, detail="已通过校验，查询安全")


async def _execute_sql(service, sql: str) -> dict[str, Any]:
    """执行 SQL 或读取缓存。"""
    cache_key = service.result_cache.make_key(sql, settings.db_url)
    cached = await service.result_cache.get(cache_key)
    info, started = start_step("执行查询", "缓存命中，跳过 DB" if cached else "正在数据库中执行查询...")
    if cached is not None:
        return {"step": finish_step(info, started, detail=f"缓存命中: {cached.row_count} 行"), "result": cached, "cache_hit": True}
    try:
        result = await service.connector.execute_query(sql, timeout=settings.safety_query_timeout)
        await service.result_cache.set(cache_key, result)
        detail = f"返回 {result.row_count} 行，耗时 {result.execution_time_ms}ms"
        return {"step": finish_step(info, started, detail=detail), "result": result, "cache_hit": False}
    except Exception as exc:  # noqa: BLE001
        return {"step": finish_step(info, started, detail=f"执行失败: {exc}", status="error"), "result": None, "error": str(exc)}


def _masked_result(service, sql: str, result: QueryResult) -> QueryResult:
    """按列级保护策略脱敏结果。"""
    display_rows, _ = service.masker.apply_to_rows(list(result.columns), [list(row) for row in result.rows])
    return QueryResult(columns=list(result.columns), rows=display_rows, row_count=result.row_count, execution_time_ms=result.execution_time_ms)


async def _interpret(service, question: str, sql: str, result: QueryResult, total_usage: UsageInfo) -> tuple[str, UsageInfo]:
    """解读结果并返回答案和累计用量。"""
    info, started = start_step("解读结果", "正在用 LLM 解读查询结果...")
    answer, usage = await interpret_result(service, question, sql, result)
    total_usage = total_usage + usage
    yield_event = finish_step(info, started, detail="已生成自然语言回答" + token_note(usage))
    service._last_interpret_step = yield_event
    return answer, total_usage


async def _chart_events(service, question: str, sql: str, result: QueryResult, total_usage: UsageInfo):
    """在需要时生成图表事件。"""
    if getattr(service, "_last_interpret_step", None):
        yield service._last_interpret_step
        yield StreamEvent("usage", asdict(total_usage))
    if not settings.chart_enabled:
        return
    info, started = start_step("生成图表", "正在选择 Vega-Lite 图表配置...")
    chart_spec, usage = await generate_chart(service, question, sql, result, suggest_visualization(sql, result))
    total_usage = total_usage + usage
    if chart_spec:
        yield finish_step(info, started, detail="已生成 Vega-Lite 图表配置")
        yield StreamEvent("chart", {"spec": chart_spec})
    else:
        yield finish_step(info, started, detail="无合适图表，跳过")
    yield StreamEvent("usage", asdict(total_usage))
