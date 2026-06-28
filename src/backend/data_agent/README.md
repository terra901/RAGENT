# data_agent

后端 Python 包根目录。这里放 FastAPI 入口、数据查询能力、运行时解耦层和基础设施代码。

## 文件夹

- `api/`: FastAPI app 和路由。
- `admin/`: 后台模型管理、密钥加密和连通性测试。
- `agent/`: LangGraph 版问数 runtime，包括独立 state、节点、graph 和 Langfuse 适配。
- `connectors/`: SQLite/PostgreSQL/MySQL 数据库连接器。
- `controllers/`: MVC Controller 层，按 API 域拆分 FastAPI 路由。
- `core/`: 应用基础设施，包括配置、日志、安全中间件和启动期迁移钩子。
- `llm/`: LLM 构建和 token usage 统计。
- `memory/`: 会话记忆、摘要和语义召回抽象。
- `models/`: Pydantic 请求/响应模型。
- `mvc/`: MVC 分层说明和扩展约定。
- `observability/`: trace 数据模型、存储、装饰器和 LangChain 回调。
- `prompts/`: LangChain prompt 入口和 Markdown 模板。
- `query_engine/`: NL2SQL、schema 上下文构建、业务语义层和图表 spec 生成。
- `repositories/`: 跨领域仓储扩展占位。
- `retrieval/`: schema / few-shot 召回、BM25、embedding 和 LangChain retriever 适配。
- `runtime/`: Celery/RabbitMQ 运行时和任务状态仓储。
- `safety/`: SQL 安全校验和敏感数据脱敏。
- `services/`: FastAPI 与具体 runtime 的解耦层。
- `storage/`: 会话历史、SQL 结果缓存和反馈元数据的存储协议、内存/Redis/SQLite 实现。
- `tasks/`: Celery 异步任务入口。

## 根文件

- `__init__.py`: 标记 `data_agent` 为 Python 包。
