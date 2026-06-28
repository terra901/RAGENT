# Prompt 模板

这一目录的 `.md` 文件是基础问数服务使用的 system prompt 模板。修改任一文件并重启进程后立即生效，无需改 Python 代码。

| 文件 | 用途 | 占位符 |
| ---- | ---- | ------ |
| `nl2sql.md` | 自然语言 → SQL | `{dialect}`、`{few_shot}` |
| `interpret_single.md` | 单步结果解读 | — |
| `chart_hint.md` | Vega-Lite 图表字段映射建议 | — |

## 写法约定

1. **`{var}` 占位符**：会被 `ChatPromptTemplate` 填充。表格里列出的变量名才会被替换；写其他 `{xxx}` 会报 `KeyError`。
2. **字面 `{` / `}`**（JSON 示例、`{{"key": ...}}` 等）必须双写 `{{` / `}}`，否则 LangChain 当作占位符解析报错。
3. **不要改文件名**：加载器按文件名硬编码读取；想新增 prompt 请同时改 `prompts/__init__.py` 的 `load_system_prompt` 调用方。

## 修改后如何验证

```bash
# 1. 重启服务
python run.py

# 2. 跑回归或至少编译检查
python -m compileall data_agent
```

提交前用 `grep -n '{[a-z_]*}' data_agent/prompts/templates/*.md` 复查占位符，确认没有遗漏的单花括号。
