# prompts

Prompt 入口目录。Python 文件定义 LangChain prompt，Markdown 模板放在 `templates/`。

## 文件

- `__init__.py`: 提供 `load_system_prompt()`，从 `templates/*.md` 读取 system prompt。
- `chart.py`: 图表建议 prompt。
- `interpret.py`: 查询结果解读 prompt。
- `nl2sql.py`: 自然语言转 SQL prompt。

## 文件夹

- `templates/`: Markdown prompt 模板目录，每个模板用于一个具体 LLM 子任务。

