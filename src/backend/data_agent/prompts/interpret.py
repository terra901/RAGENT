from langchain_core.prompts import ChatPromptTemplate

from . import load_system_prompt

INTERPRET_RESULT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", load_system_prompt("interpret_single")),
    ("user",
     "用户问题: {question}\n\n"
     "执行的 SQL:\n{sql}\n\n"
     "结果列: {columns}\n"
     "结果行数: {row_count}\n"
     "数据预览:\n{rows_preview}\n\n"
     "请用中文综合回答。"),
])
