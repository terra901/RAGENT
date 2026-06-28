# RAGENTv2 API 文档

本文档描述 `src/backend` 暴露的 HTTP/SSE 接口，以及后续接入 agent 编排运行时的扩展约定。

## 基础信息

- Base URL: `http://{DA_HOST}:{DA_PORT}`
- 前端入口: `GET /ui/`
- API 前缀: `/api`
- 认证: 配置 `DA_API_KEY` 后，`/api/ask*` 与 `/api/history*` 需要 `Authorization: Bearer <DA_API_KEY>`。
- 默认运行时: `BasicQueryService`，只包含基础问数流程，不包含 agent 节点编排。

## 端点

### GET /api/health

服务健康检查。

响应:

```json
{
  "status": "ok",
  "runtime": "basic-query-service",
  "resume_supported": false,
  "tables": ["users"],
  "llm_model": "gpt-4o",
  "llm_base_url": "https://api.openai.com/v1",
  "cache_stats": {"hits": 0, "misses": 0, "evictions": 0},
  "table_count": 1
}
```

当 `DA_HEALTH_VERBOSE=false` 时，仅返回基础状态、运行时和表数量。

### GET /api/schema

返回当前缓存的数据库表结构。

响应:

```json
{
  "tables": [
    {
      "name": "users",
      "comment": null,
      "row_count": 100,
      "columns": [
        {
          "name": "id",
          "data_type": "INTEGER",
          "nullable": false,
          "comment": null,
          "is_primary_key": true
        }
      ]
    }
  ]
}
```

### POST /api/ask

同步问数接口。适合后端调用方一次性拿完整结果。

请求:

```json
{
  "question": "上个月每天的订单量",
  "session_id": "default"
}
```

响应:

```json
{
  "answer": "上个月共有 ...",
  "sql": "SELECT ... LIMIT 100;",
  "columns": ["day", "order_count"],
  "rows": [["2026-05-01", 10]],
  "row_count": 31,
  "execution_time_ms": 120.5,
  "visualization_hint": "line",
  "chart_spec": {},
  "steps": [{"name": "生成 SQL", "status": "done", "detail": "...", "elapsed_ms": 80.2}],
  "total_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "model_calls": 2},
  "cache_hit": false,
  "memory_used": false,
  "trace_id": "optional",
  "thread_id": "default:abc123"
}
```

### POST /api/ask/stream

流式问数接口。返回 `text/event-stream`，前端默认消费此接口。

请求体与 `/api/ask` 相同。

SSE 事件:

| event | data |
| --- | --- |
| `step` | `{name,status,detail,elapsed_ms}` |
| `sql_chunk` | `{text}` 或 `{discard:true}`，LLM SQL token 流 |
| `sql` | `{sql,attempt,corrected?}`，最终 SQL 或安全校验改写后 SQL |
| `rows` | `{columns,rows,row_count,cache_hit,masked_columns?}` |
| `answer_chunk` | `{text}`，回答 token 流 |
| `chart` | `{spec}`，Vega-Lite v5 spec |
| `usage` | `{prompt_tokens,completion_tokens,total_tokens,model_calls}` |
| `done` | 最终汇总，包含 `answer/execution_time_ms/visualization_hint/chart_spec/total_usage/cache_hit/row_count/memory_used/thread_id/trace_id` |
| `error` | `{message,...}` |

示例片段:

```text
event: step
data: {"name":"检索表结构","status":"done","detail":"已加载 3/12 张表","elapsed_ms":2.1}

event: sql
data: {"sql":"SELECT ... LIMIT 100;","attempt":1}

event: done
data: {"answer":"...","row_count":31,"thread_id":"default:abc123"}
```

### GET /api/history/{session_id}

读取会话历史。

响应:

```json
{
  "session_id": "default",
  "history": [{"question": "Q", "answer": "A"}]
}
```

### DELETE /api/history/{session_id}

清空会话历史。

响应:

```json
{"status": "cleared", "session_id": "default"}
```

### POST /api/ask/resume

预留给后续 agent/HIL 的恢复接口。默认 `BasicQueryService` 返回 `503`。

请求:

```json
{
  "thread_id": "default:abc123",
  "session_id": "default",
  "user_input": {"approved": true}
}
```

接入支持 resume 的 runtime 后，响应协议与 `/api/ask/stream` 相同。

### Feedback

`DA_FEEDBACK_ENABLED=true` 时启用。

- `POST /api/feedback`: 新增反馈 `{question, sql, status, note?}`
- `GET /api/feedback?status=approved&limit=200`: 列表
- `POST /api/feedback/{fid}/approve`: 审核通过
- `POST /api/feedback/{fid}/reject`: 驳回
- `DELETE /api/feedback/{fid}`: 删除

### Trace

`DA_TRACE_API_ENABLED=true` 时启用。

- `GET /api/traces`
- `GET /api/traces/{trace_id}`
- `DELETE /api/traces/{trace_id}`

## Agent Runtime 接入约定

HTTP 路由只依赖 `data_agent.services.AgentRuntime` 协议，不直接依赖任何 agent 编排实现。

后续要接 agent 编排时，实现一个工厂函数:

```python
from data_agent.services import RuntimeDependencies


def build_agent_runtime(deps: RuntimeDependencies):
    return YourAgentRuntime(
        connector=deps.connector,
        schema_manager=deps.schema_manager,
        llm=deps.llm,
        result_cache=deps.result_cache,
        session_store=deps.session_store,
        feedback_store=deps.feedback_store,
        memory_provider=deps.memory_provider,
    )
```

然后配置:

```bash
DA_AGENT_RUNTIME_FACTORY=your_package.your_module:build_agent_runtime
```

`YourAgentRuntime` 需要实现:

- `initialize()` / `shutdown()`
- `ask(question, session_id)`
- `ask_stream(question, session_id)`
- `ask_resume(thread_id, user_input)`
- `get_history_async(session_id)` / `clear_history_async(session_id)`
- 属性: `schema_manager`、`result_cache`、`feedback_store`、`supports_resume`、`runtime_name`

只要输出同一套 `StreamEvent` 事件，前端和 HTTP API 不需要改动。

