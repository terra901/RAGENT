from langchain_core.prompts import ChatPromptTemplate

from . import load_system_prompt

CHART_HINT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", load_system_prompt("chart_hint")),
    ("user",
     "用户问题: {question}\n"
     "结果列摘要: {columns_summary}\n\n"
     "请输出图表建议 JSON。"),
])
