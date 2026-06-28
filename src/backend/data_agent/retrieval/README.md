# retrieval

召回与检索目录。这里放 schema 召回、few-shot 召回和 embedding 适配，不直接生成 SQL，也不直接执行数据库查询。

## 文件

- `__init__.py`: 标记 `retrieval` 为 Python 子包。
- `recall.py`: schema 召回的 BM25 与 embedding 基础实现。
- `retriever.py`: LangChain 风格的 schema ensemble retriever，供 `query_engine.schema_manager` 使用。
- `embeddings.py`: fastembed provider 工厂，用于 schema、memory 和 few-shot 语义召回。
- `feedback_retriever.py`: 用户反馈 few-shot 的 BM25/语义融合召回，供 `storage.feedback_store` 使用。

## 引用关系

- `query_engine/schema_manager.py` 依赖 `recall.py` 和 `retriever.py` 来从所有表中选出与当前问题最相关的表。
- `api/main.py` 在开启 embedding 时通过 `embeddings.py` 创建默认 embedding provider。
- `memory/_factory.py` 复用 `retriever.py` 里的 LangChain embedding 适配器。
- `storage/feedback_store.py` 使用 `feedback_retriever.py` 从已批准反馈中召回 few-shot 示例。
