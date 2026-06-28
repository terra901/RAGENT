# data

后端本地运行数据目录。

## 业务库

当前业务查询库使用本机 MySQL `RAGENT` 数据库，默认连接配置在 `../.env` 和 `data_agent/core/config.py`：

```text
mysql+asyncmy://root:<password>@127.0.0.1:3306/RAGENT?charset=utf8mb4
```

`generated/` 目录保存已准备好的 MySQL 兼容建表资料：

- `generated/ragent_mysql_schema.sql`: `RAGENT` 库 ADS/DWS V4 表结构 DDL。
- `generated/ragent_mysql_schema_report.txt`: 表结构、业务口径和查询说明。

当前本机 MySQL `RAGENT` 库已注入演示数据：10 张业务表，每张 200 行。
示例数据脚本：

```bash
python3 scripts/seed_ragent_mysql_demo.py
```

默认只允许向空表注入，避免误追加。需要重置演示数据时显式使用：

```bash
python3 scripts/seed_ragent_mysql_demo.py --replace
```

## 运行期元数据

以下文件由后端按需生成，和业务库隔离：

- `feedback.db`: few-shot 反馈库。
- `memory.db`: RAG / Memory sqlite-vec 库。
- `trace.db`: trace/span 观测库。
