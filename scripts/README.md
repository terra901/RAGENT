# scripts

项目级运维脚本目录，负责一键启动/停止完整 RAGENT 本地实例。

## 文件树

```text
scripts/
├── README.md              # 当前目录说明
├── start_ragent_full.sh   # 启动 Docker 依赖、后端 API、Celery worker
└── stop_ragent_full.sh    # 停止后端 API、Celery worker，可选停止 Docker 依赖
```

## 设计说明

- PID 文件写入项目根目录 `.runtime/`。
- 日志写入项目根目录 `logs/`。
- Docker 数据卷默认保留，避免误删 MySQL/Redis/RabbitMQ 数据。
