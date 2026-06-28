"""NL2SQL 管道：LangChain Runnable 版本，含 stream + retry。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from ..core.config import settings
from ..llm.usage import UsageInfo, extract_usage  # UsageInfo 已移至 llm.usage，无循环依赖
from ..core.logging import get_logger
from ..prompts.nl2sql import NL2SQL_PROMPT
from ..safety.validator import SafetyValidator, _strip_literals_and_comments

log = get_logger(__name__)


@dataclass
class StreamChunk:
    """流式回调的 payload。

    - text:    本次 chunk 的增量文本（非空表示有内容）
    - discard: True 表示前面累积的 chunks 应被丢弃（attempt 失败前的 reset）
    """
    text: str = ""
    discard: bool = False


ChunkCallback = Callable[[StreamChunk], Awaitable[None]]


# 按方言切换的 few-shot；新增方言时在此扩展
FEW_SHOT_BY_DIALECT: dict[str, list[dict[str, str]]] = {
    "sqlite": [
        {"question": "有多少用户？", "sql": "SELECT COUNT(*) AS user_count FROM users;"},
        {
            "question": "销售额最高的前5个产品是什么？",
            "sql": (
                "SELECT p.name, SUM(o.amount) AS total_sales "
                "FROM orders o JOIN products p ON o.product_id = p.id "
                "GROUP BY p.name ORDER BY total_sales DESC LIMIT 5;"
            ),
        },
        {
            "question": "上个月每天的订单量",
            "sql": (
                "SELECT DATE(created_at) AS day, COUNT(*) AS order_count "
                "FROM orders WHERE created_at >= DATE('now', '-1 month') "
                "GROUP BY DATE(created_at) ORDER BY day;"
            ),
        },
        {
            "question": "每个分类的平均价格",
            "sql": (
                "SELECT category, AVG(price) AS avg_price "
                "FROM products GROUP BY category ORDER BY avg_price DESC;"
            ),
        },
    ],
    "postgres": [
        {"question": "有多少用户？", "sql": "SELECT COUNT(*) AS user_count FROM users;"},
        {
            "question": "上个月每天的订单量",
            "sql": (
                "SELECT DATE_TRUNC('day', created_at) AS day, COUNT(*) AS order_count "
                "FROM orders WHERE created_at >= NOW() - INTERVAL '1 month' "
                "GROUP BY day ORDER BY day;"
            ),
        },
    ],
    "mysql": [
        {
            "question": "最近 30 天每个广告平台的消耗和 ROI",
            "sql": (
                "SELECT ad_pmedia, SUM(spend) AS spend, "
                "SUM(pay_amt_sum) / 100 / NULLIF(SUM(spend), 0) AS roi "
                "FROM ads_buy_channel_roi_daily "
                "WHERE stat_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) "
                "GROUP BY ad_pmedia ORDER BY roi DESC LIMIT 20;"
            ),
        },
        {
            "question": "最近 7 天每天的 DAU 和收入",
            "sql": (
                "SELECT stat_date, SUM(dau) AS dau, SUM(pay_amt_sum) / 100 AS revenue "
                "FROM ads_op_game_overview_daily "
                "WHERE stat_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) "
                "GROUP BY stat_date ORDER BY stat_date;"
            ),
        },
        {
            "question": "D7 留存最高的素材有哪些？",
            "sql": (
                "SELECT ad_material_id, "
                "SUM(retain_d7_cnt) / NULLIF(SUM(game_new_user_cnt), 0) AS retain_d7_rate "
                "FROM ads_material_daily "
                "GROUP BY ad_material_id ORDER BY retain_d7_rate DESC LIMIT 20;"
            ),
        },
    ],
}


def _system_prompt(dialect: str) -> str:
    """保留旧 prompt 逻辑（dialect_hint）以兼容使用该函数的历史代码。"""
    dialect_hint = {
        "sqlite": "目标数据库: SQLite。日期函数使用 DATE() / strftime()。",
        "postgres": "目标数据库: PostgreSQL。日期函数使用 NOW() / DATE_TRUNC() / INTERVAL。",
        "mysql": "目标数据库: MySQL。日期函数使用 NOW() / DATE_SUB() / INTERVAL。",
    }.get(dialect, "")
    return f"""你是一个精确的 SQL 查询生成器。根据用户问题和数据库 Schema 生成正确的 SQL。

规则:
1. 只生成单条 SELECT 查询（或 WITH ... SELECT），禁止任何写操作、禁止多语句。
2. 只使用 Schema 中列出的表和列。
3. 对于聚合查询，始终使用 GROUP BY。
4. JOIN 时使用明确的连接条件。
5. 输出 SQL 必须以分号结尾，前后不要加任何解释，不要用代码块包裹。
{dialect_hint}
"""


@dataclass
class NL2SQLResult:
    """封装 NL2SQLResult 的数据结构或业务行为。"""
    sql: str
    thought: str = ""
    retries: int = 0
    usage: UsageInfo = field(default_factory=UsageInfo)
    sql_raw: str = ""  # LLM 原始 SQL(SafetyValidator 注入 LIMIT 之前),供 n_execute_hil 静态 risk 检测


def _format_few_shot(examples: list[dict[str, str]]) -> str:
    """格式化 format_few_shot 对应的展示内容。"""
    return "".join(f"问题: {ex['question']}\nSQL: {ex['sql']}\n\n" for ex in examples)


class NL2SQLChain:
    """自然语言转 SQL Chain（LangChain Runnable 版本），含 stream + retry。"""

    def __init__(
        self,
        llm: BaseChatModel,
        validator: SafetyValidator | None = None,
        max_retries: int = 3,
        dialect: str = "sqlite",
        feedback_store=None,
    ):
        """初始化当前对象的依赖和内部状态。"""
        self.llm = llm
        self.dialect = dialect
        self.validator = validator or SafetyValidator(
            max_rows=settings.safety_max_rows,
            dialect=dialect,
        )
        self.max_retries = max_retries
        # FeedbackStore（可选）：拼自学习 few-shot
        self.feedback_store = feedback_store

    async def generate(
        self,
        question: str,
        schema_context: str,
        conversation_history: str = "",
        prior_attempts: list[tuple[str, str]] | None = None,
        chunk_cb: ChunkCallback | None = None,
    ) -> NL2SQLResult:
        """生成 SQL。max_retries 校验循环 + 流式 chunk + prior_attempts 注入。

        prior_attempts: 上轮失败的 (sql, error) 对，用于把执行错误回填给 LLM 修正。
        chunk_cb: 可选流式回调；非 None 时以 astream_events 调用 LLM。
                  attempt > 1 时（重试）会先回调一次 discard=True 让前端清空累积。
        """
        examples = FEW_SHOT_BY_DIALECT.get(self.dialect, FEW_SHOT_BY_DIALECT["sqlite"])
        few_shot = _format_few_shot(examples)

        # 自学习 few-shot：从反馈库召回 top-K (Q, SQL) 拼接（已审核 approved）
        if self.feedback_store is not None:
            try:
                hits = self.feedback_store.recall(question)
                if hits:
                    few_shot += "\n-- 历史正确范例（用户审核通过）:\n" + _format_few_shot(
                        [{"question": h.question, "sql": h.sql} for h in hits]
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("FeedbackStore.recall 失败，跳过自学习 few-shot: %s", e)

        # 对话历史作为 MessagesPlaceholder
        from langchain_core.messages import HumanMessage
        history_msgs: list = []
        if conversation_history:
            history_msgs.append(HumanMessage(content=f"（对话历史）\n{conversation_history}"))

        # 构建 prior_attempts_block（执行阶段错误回填）
        prior_block_str = ""
        if prior_attempts:
            prior_block_str = "\n".join(
                f"上一次尝试失败：\nSQL: {prev_sql}\n错误: {prev_err}"
                for prev_sql, prev_err in prior_attempts
            ) + "\n\n"

        chain = NL2SQL_PROMPT | self.llm
        cumulative_usage = UsageInfo()
        last_raw = ""

        for attempt in range(1, self.max_retries + 1):
            # 重试时通知前端：之前累积的 chunks 应被丢弃
            if chunk_cb and attempt > 1:
                await chunk_cb(StreamChunk(discard=True))

            inputs = {
                "dialect": self.dialect,
                "few_shot": few_shot,
                "schema_context": schema_context,
                "prior_attempts_block": prior_block_str,
                "question": question,
                "history": history_msgs,
            }
            raw, call_usage = await self._call_chain(chain, inputs, chunk_cb)
            cumulative_usage = cumulative_usage + call_usage
            last_raw = raw

            sql = self._extract_sql(raw)
            if not sql:
                log.info("Attempt %d: 未提取到有效单语句 SQL，反馈重试", attempt)
                prior_block_str += "上一次返回非法格式或多语句，请只输出一条 SELECT。\n\n"
                continue

            validation = self.validator.validate(sql)
            if validation.is_valid:
                return NL2SQLResult(
                    sql=validation.corrected_sql or sql,
                    sql_raw=sql,  # Phase 4: SafetyValidator 注入 LIMIT 之前的 LLM 原始 SQL
                    thought=raw,
                    retries=attempt - 1,
                    usage=cumulative_usage,
                )
            # 校验失败：把错误回填到 prior_block_str
            err_msg = '; '.join(validation.errors)
            prior_block_str += (
                f"上一次 SQL 校验失败：\nSQL: {sql}\n错误: {err_msg}\n"
                "请修正后重新生成只读 SELECT。\n\n"
            )

        log.warning("NL2SQL exhausted %d retries", self.max_retries)
        return NL2SQLResult(sql="", thought=last_raw, retries=self.max_retries, usage=cumulative_usage)

    async def _call_chain(
        self,
        chain,
        inputs: dict,
        chunk_cb: ChunkCallback | None,
    ) -> tuple[str, UsageInfo]:
        """统一 LangChain chain 调用入口。chunk_cb 非 None 时走 astream_events 流式。"""
        if chunk_cb is None:
            msg: AIMessage = await chain.ainvoke(inputs)
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            return text, extract_usage(msg)

        # 流式：通过 astream_events v2 接收增量 token
        parts: list[str] = []
        final_msg: AIMessage | None = None
        async for event in chain.astream_events(inputs, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                delta = event["data"]["chunk"]
                t = delta.content if isinstance(delta.content, str) else ""
                if t:
                    parts.append(t)
                    await chunk_cb(StreamChunk(text=t))
            elif kind == "on_chat_model_end":
                final_msg = event["data"]["output"]
        usage = extract_usage(final_msg) if final_msg else UsageInfo()
        return "".join(parts), usage

    @staticmethod
    def _extract_sql(text: str) -> str:
        """从 LLM 回复提取单条 SQL。多语句返回空串以触发重试。"""
        text = (text or "").strip()
        code_block = re.search(r"```(?:sql)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        candidate = code_block.group(1).strip() if code_block else text

        m = re.search(r"\b(SELECT|WITH)\b.*", candidate, re.DOTALL | re.IGNORECASE)
        if not m:
            return ""
        body = m.group(0).strip().rstrip(";").strip()

        # 剥离字符串/注释后再判定是否多语句
        if ";" in _strip_literals_and_comments(body):
            return ""
        return body + ";"


# 兼容别名：外部代码可继续用 NL2SQLPipeline 这个旧类名
NL2SQLPipeline = NL2SQLChain
