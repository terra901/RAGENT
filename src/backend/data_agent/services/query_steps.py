"""问数运行时的可复用步骤函数。"""
from __future__ import annotations

import time
from dataclasses import asdict

from langchain_core.messages import AIMessage

from ..connectors.base import QueryResult
from ..llm.usage import UsageInfo, extract_usage
from ..observability.decorators import traced
from ..query_engine.chart_generator import generate_chart_spec
from ..query_engine.nl2sql import NL2SQLChain, StreamChunk
from .agent_port import StepInfo, StreamEvent


def dialect_from_url(db_url: str) -> str:
    """根据 SQLAlchemy URL 推断 SQL 方言。"""
    head = db_url.split(":", 1)[0].lower()
    if head.startswith("sqlite"):
        return "sqlite"
    if head.startswith(("postgres", "postgresql")):
        return "postgres"
    if head.startswith("mysql"):
        return "mysql"
    return "sqlite"


def start_step(name: str, detail: str = "") -> tuple[StepInfo, float]:
    """创建运行中步骤并记录开始时间。"""
    return StepInfo(name=name, status="running", detail=detail), time.perf_counter()


def finish_step(info: StepInfo, started_at: float, *, detail: str | None = None, status: str = "done") -> StreamEvent:
    """结束步骤并转换成流式事件。"""
    info.elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    if detail is not None:
        info.detail = detail
    info.status = status
    return StreamEvent("step", asdict(info))


def make_nl2sql_chain(service) -> NL2SQLChain:
    """创建绑定当前 LLM 和 SQL 方言的 NL2SQL 链。"""
    return NL2SQLChain(llm=service.llm, dialect=service._dialect, feedback_store=service.feedback_store)


def token_note(usage: UsageInfo, retries: int = 0) -> str:
    """格式化 token 用量和重试次数。"""
    retry_note = f" ({retries} 次重试)" if retries else ""
    if not usage.total_tokens:
        return retry_note
    return f"{retry_note} | token 总数: {usage.total_tokens} (提示 {usage.prompt_tokens}, 生成 {usage.completion_tokens})"


@traced(kind="chain", name="interpret_result", capture_io=False)
async def interpret_result(service, question: str, sql: str, result: QueryResult, chunk_cb=None) -> tuple[str, UsageInfo]:
    """请求 LLM 用自然语言解读查询结果。"""
    from ..prompts.interpret import INTERPRET_RESULT_PROMPT

    if result.row_count == 0:
        return "查询结果为空，建议放宽筛选条件或检查数据是否存在。", UsageInfo()
    cols = ", ".join(result.columns)
    sample_rows = result.rows[:20]
    rows_preview = "\n".join(" | ".join(str(v) for v in row) for row in sample_rows)
    if result.row_count > 20:
        rows_preview += f"\n... (仅显示前 20 行，共 {result.row_count} 行)"
    inputs = {"question": question, "sql": sql, "columns": cols, "row_count": result.row_count, "rows_preview": rows_preview or "(空)"}
    chain = INTERPRET_RESULT_PROMPT | service.llm
    try:
        if chunk_cb is None:
            msg: AIMessage = await chain.ainvoke(inputs)
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            return text, extract_usage(msg)
        parts: list[str] = []
        final_msg: AIMessage | None = None
        async for event in chain.astream_events(inputs, version="v2"):
            if event["event"] == "on_chat_model_stream":
                text = event["data"]["chunk"].content
                if isinstance(text, str) and text:
                    parts.append(text)
                    await chunk_cb(StreamChunk(text=text))
            elif event["event"] == "on_chat_model_end":
                final_msg = event["data"]["output"]
        return "".join(parts), extract_usage(final_msg) if final_msg else UsageInfo()
    except Exception as exc:  # noqa: BLE001
        service_log(service).warning("解读结果的 LLM 调用失败: %s", exc)
        return f"查询返回 {result.row_count} 行数据，共 {len(result.columns)} 列。", UsageInfo()


@traced(kind="chain", name="generate_chart", capture_io=False)
async def generate_chart(service, question: str, sql: str, result: QueryResult, viz_hint: str | None) -> tuple[dict | None, UsageInfo]:
    """在适合可视化时生成安全 Vega-Lite 配置。"""
    return await generate_chart_spec(
        service.llm,
        question=question,
        sql=sql,
        columns=list(result.columns),
        rows=[list(row) for row in result.rows],
        viz_hint=viz_hint,
    )


def suggest_visualization(sql: str, result: QueryResult) -> str:
    """根据 SQL 和结果形状返回轻量级可视化建议。"""
    sql_upper = sql.upper()
    if result.row_count <= 1:
        return "table"
    if any(kw in sql_upper for kw in ("DATE", "MONTH", "YEAR", "STRFTIME", "DATE_TRUNC", "GROUP BY")):
        for col in result.columns:
            if any(t in col.lower() for t in ("date", "time", "month", "year", "day", "季度", "周")):
                return "line"
        if result.rows and any(isinstance(value, (int, float)) for value in result.rows[0]):
            return "bar"
    if any(kw in sql_upper for kw in ("RATIO", "PERCENT", "SHARE", "占比", "百分比")):
        return "pie"
    if "ORDER BY" in sql_upper and "DESC" in sql_upper and result.row_count <= 20:
        return "bar"
    return "table"


def analyze_intent(question: str) -> list[str]:
    """提取简单关键词类别，用于用户可见步骤反馈。"""
    query = question.lower()
    intent_map = {
        "count": ["多少", "数量", "count", "几个", "几条"],
        "sum": ["总额", "总计", "合计", "sum", "total", "销售额", "收入"],
        "avg": ["平均", "avg", "average"],
        "rank": ["排名", "前", "top", "排行"],
        "trend": ["趋势", "变化", "增长", "下降"],
        "time": ["今天", "昨天", "上个月", "本月", "年", "月", "日", "周"],
    }
    return [name for name, terms in intent_map.items() if any(term in query for term in terms)]


def service_log(service):
    """读取服务实例日志对象。"""
    import logging

    return getattr(service, "log", logging.getLogger(__name__))
