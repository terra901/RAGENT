# agent

LangGraph 版问数运行时。

## 文件

- `state.py`: 定义可在节点间传递的 `AgentState`。
- `context.py`: 定义不可序列化的请求级 `RunContext`，例如 runtime、事件队列和 Langfuse observer。
- `graph.py`: 只定义图结构和条件路由，业务逻辑放在节点文件里。
- `runtime.py`: 实现 `services.AgentRuntime`，供 `DA_AGENT_RUNTIME_FACTORY` 接入。
- `langfuse.py`: Langfuse 可观测适配器；默认指向本地 self-host Langfuse，未启用或未配置 key 时为 no-op。
- `utils.py`: 节点共享的步骤、usage、结果转换工具。
- `nodes/`: 每个图节点一个 Python 文件。

## 节点顺序

```text
load_memory
  -> recall_schema
  -> generate_sql
  -> validate_sql
  -> execute_sql
  -> interpret_result
  -> generate_chart
  -> persist_memory
```

`execute_sql` 失败且未超过重试次数时会回到 `generate_sql`，并把失败 SQL 和错误信息写入 `prior_attempts`。

## Langfuse 观测点

Langfuse 不在 `graph.py` 里实现。`runtime.py` 创建 `LangfuseObserver`，通过
`RunContext` 注入每个节点；顶层 `data_agent.graph` 包住一次完整问答，每个节点
再记录自己的 child observation。

- LLM 节点：`generate_sql`、`interpret_result`、`generate_chart`，使用 `generation`。
- 工具节点：`execute_sql`，使用 `tool`。
- 安全节点：`validate_sql`，使用 `guardrail`。
- 其他节点：memory/schema/persist 使用 `span` 或 `retriever`。

本地部署和 `.env` 配置见 `../observability/LANGFUSE_LOCAL.md`。
