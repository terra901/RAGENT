# RAGENTv2 Backend

这个目录是从 `r-data-agent` 迁移出的后端基础能力，不包含 agent 节点编排。

## 目录

- `data_agent/api`: FastAPI 路由与应用入口
- `data_agent/agent`: LangGraph 版问数 runtime、节点、state 和 Langfuse 适配
- `data_agent/services`: API 与运行时之间的解耦层
- `data_agent/core`: 配置、日志、安全中间件和启动期迁移钩子
- `data_agent/storage`: 会话历史、SQL 结果缓存和反馈元数据存储
- `data_agent/connectors`: SQLite/PostgreSQL/MySQL 连接器
- `data_agent/query_engine`: NL2SQL、Schema 上下文、业务语义层和图表生成
- `data_agent/retrieval`: Schema / few-shot 召回、BM25、embedding 和 retriever 适配
- `data_agent/safety`: SQL 安全校验与列级脱敏
- `data_agent/observability`: trace 存储与 LangChain tracing
- `deploy/langfuse`: 本地 self-host Langfuse Docker Compose 栈
- `data/generated`: RAGENT MySQL 兼容表结构和业务说明

前端静态应用位于 `../frontend`，由 FastAPI 挂载到 `/ui/`。

## 文件

- `.env`: 后端唯一环境配置文件，包含数据库、LLM、鉴权、运行时工厂等配置项。
- `pyproject.toml`: 原项目的 Python 包元数据和可选依赖声明，保留作包化参考。
- `requirements.txt`: 当前推荐安装文件，列出 FastAPI 后端运行所需依赖。
- `run.py`: 开发启动入口，调用 Uvicorn 加载 `data_agent.api.main:app`。
- `semantic_layer.json`: RAGENT ADS/DWS 语义层配置，用于定义表、指标、维度和同义词。
- `server.py`: 单进程启动入口，会根据配置启动服务并自动打开浏览器。

## 启动

```bash
cd /home/chenjy/桌面/RAGENTv2/src/backend
python3 -m pip install -r requirements.txt
# .env 已指向本机 MySQL RAGENT 库；如账号不同，修改 DA_DB_URL
python3 run.py
```

打开 `http://127.0.0.1:8000/ui/`。

## Agent 接入

当前 `.env` 默认使用 `data_agent.agent.runtime:build_agent_runtime`。如果需要替换 agent 编排，不需要改 API 路由，只需要实现 `data_agent.services.AgentRuntime` 并配置:

```bash
DA_AGENT_RUNTIME_FACTORY=your_package.your_module:build_agent_runtime
```

接口协议见 [../../docs/API.md](../../docs/API.md)。
