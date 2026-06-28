# observability

观测和 trace 目录。用于记录请求级 trace、span 树和 LLM 调用信息。

## 文件

- `__init__.py`: 标记 `observability` 为 Python 子包。
- `decorators.py`: 提供 `traced()` 装饰器和输入输出脱敏过滤。
- `models.py`: 定义 `Trace` 和 `Span` 数据结构。
- `trace_store.py`: SQLite trace 存储，包含异步写队列、查询、删除和清理。
- `tracer.py`: 请求 trace 管理器和 LangChain callback handler。
- `LANGFUSE_LOCAL.md`: 本地 self-host Langfuse 的接入边界、`.env` 配置和 agent 观测点说明。

## 边界

`observability/` 里的 SQLite trace 是 RAGENT 内置本地 trace；Langfuse 是可选外部观测服务。
当前仓库不依赖 Langfuse Cloud，默认 host 为本地 `http://127.0.0.1:3000`。
