# services

运行时服务层。它是 FastAPI 和后续 agent 编排之间的适配边界。

## 文件

- `__init__.py`: 汇总导出 runtime 协议、默认实现和工厂。
- `agent_port.py`: 定义 `AgentRuntime` 协议、`AskResult`、`StepInfo` 和 `StreamEvent`。
- `basic_query_service.py`: 默认基础问数 runtime，不包含 agent 节点编排。
- `factory.py`: 根据 `DA_AGENT_RUNTIME_FACTORY` 创建默认 runtime 或自定义 agent runtime。
- `query_steps.py`: 问数流程步骤和事件构造辅助。
- `query_stream.py`: 默认 runtime 的流式执行编排。
- `admin/`: 后台管理服务扩展点。
