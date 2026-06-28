# core

应用基础设施模块。

- `config.py`: 环境变量和 `.env` 配置入口，导出 `Settings` 与全局 `settings`。
- `logging.py`: 全局日志初始化与 `get_logger()`。
- `security.py`: FastAPI API Key 鉴权和进程内限流中间件。
- `migrations.py`: 启动期运行数据布局迁移钩子；当前 MySQL 业务库场景为 no-op。
