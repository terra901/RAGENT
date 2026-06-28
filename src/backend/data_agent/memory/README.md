# memory

会话记忆目录。默认使用 Hermes 记忆保存最近轮次和摘要；启用 vec/embedding 时升级为摘要、窗口和语义召回组合。

## 文件树

```text
memory/
├── __init__.py       # 导出 memory 类和 make_memory_provider()
├── _factory.py       # 根据配置装配 Hermes/Combined/Null 记忆
├── hermes.py         # Hermes 记忆后备：摘要 + 最近窗口
├── provider.py       # Memory 协议、上下文、空实现和组合实现
└── summary_store.py  # 摘要存储协议及内存、SQLite、Redis 实现
```

## 设计说明

- Hermes 不依赖向量库，Redis 可用时摘要写入 Redis，否则写入 SQLite。
- `CombinedMemoryProvider` 在 embedding/sqlite-vec 可用时增加语义召回。
- Agent 图中的 `load_memory` 和 `persist_memory` 节点统一使用 `MemoryProvider` 协议。
