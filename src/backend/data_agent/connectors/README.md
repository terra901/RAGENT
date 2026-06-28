# connectors

数据库连接器目录。所有连接器实现同一个 `BaseConnector` 抽象，供 `query_engine` 和 runtime 统一调用。

## 文件

- `__init__.py`: 暴露 `make_connector()`，按数据库 URL 协议选择 SQLite、PostgreSQL 或 MySQL 连接器。
- `base.py`: 定义 `ColumnInfo`、`TableInfo`、`QueryResult` 和 `BaseConnector` 抽象接口。
- `sqlite.py`: SQLite async 连接器，负责表结构读取、只读保护、查询执行和 explain。
- `postgres.py`: PostgreSQL async 连接器，负责 information_schema 读取、只读事务和查询执行。
- `mysql.py`: MySQL async 连接器，负责 information_schema 读取、只读事务和查询执行。
