# composables

前端可复用逻辑目录，封装 API 调用、会话、健康检查、schema、SSE 和图表加载。

## 文件

- `useApiFetch.js`: 统一 fetch 封装，自动注入 API Key。
- `useConversations.js`: 会话创建、删除、切换、标题更新和 localStorage 持久化。
- `useHealth.js`: 周期性调用 `/api/health` 更新后端健康状态。
- `useMarkdown.js`: Markdown 渲染和 DOMPurify XSS 净化。
- `useSchema.js`: 调用 `/api/schema` 加载数据库结构。
- `useStreaming.js`: 调用 `/api/ask/stream`，解析 SSE 并更新消息状态。
- `useVegaEmbed.js`: 懒加载 vega、vega-lite 和 vega-embed。

