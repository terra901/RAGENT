# query_engine

问数主流程目录。这里放“自然语言问题 -> SQL -> 查询结果展示建议”这条链路的核心组件，不直接负责底层存储、Redis、MySQL 连接实现或 API 路由。

## 文件

- `__init__.py`: 标记 `query_engine` 为 Python 子包。
- `chart_generator.py`: 让 LLM 输出图表字段建议，并由后端安全组装 Vega-Lite spec。
- `nl2sql.py`: 自然语言转 SQL 的 LangChain chain，包含 SQL 提取、重试和安全校验。
- `schema_manager.py`: 表结构缓存、刷新、渲染和问题驱动 schema 召回。
- `semantic_layer.py`: 业务术语、表描述、join hint 和敏感列配置加载。

## 引用关系

- `api/main.py` 启动时创建 `SchemaManager`，并加载 `semantic_layer.json` 生成 `SemanticLayer`。
- `services/basic_query_service.py` 调用 `SchemaManager.build_schema_context()` 生成 schema prompt，然后调用 `NL2SQLChain.generate()` 生成 SQL。
- `schema_manager.py` 依赖 `retrieval/` 里的 BM25、embedding 和 ensemble retriever 完成相关表召回。
- `chart_generator.py` 在 SQL 执行成功后，根据结果列和样例数据生成前端可渲染的图表 spec。
