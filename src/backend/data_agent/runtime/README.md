# runtime

异步运行时基础设施目录，承接 RabbitMQ、Celery 和队列任务状态。它不关心页面展示，只提供任务分发和状态存储能力。

## 文件树

```text
runtime/
├── __init__.py       # 包标记
├── celery_app.py     # Celery 应用实例，读取 RabbitMQ 配置
└── job_store.py      # agent_jobs MySQL 队列任务仓储
```

## 设计说明

- RabbitMQ 地址来自 `DA_CELERY_BROKER_URL`。
- `job_store.py` 用 MySQL 记录 queued/running/succeeded/failed 状态，供前端排队提示读取。
- 后续真正的长任务可以替换 `tasks/ask_tasks.py` 中的占位任务。
