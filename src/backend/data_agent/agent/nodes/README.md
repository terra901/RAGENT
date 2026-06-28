# agent/nodes

LangGraph Agent 节点目录。每个节点只完成一个阶段，便于热插拔、单测和替换。

## 文件树

```text
nodes/
├── execute_sql.py       # 执行 SQL
├── generate_chart.py    # 生成图表规格
├── generate_sql.py      # 生成 SQL
├── interpret_result.py  # 解释查询结果
├── load_memory.py       # 加载会话记忆
├── persist_memory.py    # 持久化记忆
└── validate_sql.py      # SQL 安全校验
```

## 设计说明

- 节点间通过 `agent/state.py` 交换状态。
- 新节点应保持小函数、少副作用，避免直接读写 HTTP 层对象。
