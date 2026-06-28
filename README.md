# RAGENTv2

RAGENTv2 是面向数据问答的 Agent 工作台，后端按 MVC 边界拆分，前端提供聊天、排队提示和后台管理入口。当前版本已经接入 MySQL、Redis、RabbitMQ/Celery、Hermes 记忆、OpenTelemetry trace 和后台模型管理。

## 文件和目录

- `docker-compose.yml`: RAGENT 独立 MySQL/Redis/RabbitMQ 实例，不占用 Discord-bot 容器端口。
- `docs/`: 项目级文档。
- `src/backend/`: FastAPI 后端、Agent runtime、MVC 控制器、存储、队列和观测模块。
- `src/frontend/`: Vue 3 ESM 静态前端，包含聊天界面和后台管理页面。

## 本地服务

- MySQL: `127.0.0.1:3307`，数据库 `RAGENT`，密码 `140617`。
- Redis: `127.0.0.1:6380`，密码 `140617`。
- RabbitMQ: `127.0.0.1:5673`，管理台 `127.0.0.1:15673`，账号 `ragent / 140617`。
- 默认后台管理员: `admin@ragent.local / 140617`。

## 验证命令

```bash
/home/chenjy/miniconda3/envs/RAGENT/bin/python -m compileall src/backend/data_agent src/backend/scripts src/backend/worker.py
find src/frontend -name '*.js' -print0 | xargs -0 -n1 node --check
```
