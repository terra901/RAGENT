# controllers

MVC 架构中的 Controller 层，负责 HTTP 入参、鉴权、状态码和响应结构。业务规则下沉到 `services/`、`admin/`、`storage/`、`query_engine/` 等模块。

## 文件树

```text
controllers/
├── __init__.py            # 控制器包标记
├── admin_models.py        # 后台模型管理 API
├── ask.py                 # 问数同步/流式 API
├── ask_helpers.py         # 问数控制器辅助函数
├── auth.py                # 注册、登录、刷新、登出、当前用户
├── conversations.py       # 对话列表、消息和标题管理
├── deps.py                # FastAPI 依赖注入、鉴权和权限检查
├── feedback.py            # few-shot 反馈样本 API
├── jobs.py                # RabbitMQ/Celery 队列状态和任务入口
├── system.py              # 健康检查和 schema API
├── templates.py           # SQL 模板注册表 API
└── traces.py              # 后台 trace 观测 API
```

## 设计说明

- 每个文件按业务入口拆分，避免单个路由文件膨胀。
- `deps.py` 是权限边界，后台接口统一使用 `require_admin`。
- Controller 只做编排，不保存数据库连接或全局状态。
