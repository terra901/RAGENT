# safety

安全能力目录，负责 SQL 执行前校验和查询结果对外输出前脱敏。

## 文件

- `__init__.py`: 标记 `safety` 为 Python 子包。
- `masking.py`: 根据敏感列配置对 SQL 做敏感列检查，并对结果行做脱敏。
- `validator.py`: 校验 SQL 只读、单语句、纯 SELECT/CTE，并强制注入或收紧 LIMIT。

