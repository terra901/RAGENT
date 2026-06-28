from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from . import load_system_prompt

_USER_NL2SQL = """可用 Schema:
{schema_context}

{prior_attempts_block}

用户问题：{question}

请只输出符合方言的 SQL。"""

NL2SQL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", load_system_prompt("nl2sql")),
    MessagesPlaceholder("history", optional=True),
    ("user", _USER_NL2SQL),
])
