# components

Vue 3 ESM 组件目录。每个文件导出一个前端组件。

## 文件

- `AgentMessage.js`: 渲染助手消息，包括文本、SQL、步骤、结果表、图表和 trace 链接。
- `App.js`: 前端根组件，组装侧边栏、聊天面板、后台管理和队列状态轮询。
- `ChartCard.js`: 使用 vega-embed 渲染后端返回的 Vega-Lite 图表。
- `ChatPanel.js`: 聊天主区域，包含消息列表和输入框。
- `MessageList.js`: 消息列表容器，按当前会话渲染消息。
- `QueryBox.js`: 用户输入框、发送按钮和排队提示条。
- `ResultCards.js`: 查询结果的卡片容器。
- `SchemaTree.js`: 数据库 schema 树形展示。
- `Sidebar.js`: 会话列表、健康状态和后台管理入口。
- `SpanTree.js`: Trace span 树展示。
- `SqlCard.js`: SQL 展示组件。
- `StepsCard.js`: 流式步骤展示组件。
- `TableCard.js`: 查询结果表格展示。
- `TraceDetail.js`: 单条 trace 详情展示。
- `TraceList.js`: trace 列表展示和刷新。
- `TracePanel.js`: Trace 抽屉面板。
- `UserMessage.js`: 用户消息展示。
