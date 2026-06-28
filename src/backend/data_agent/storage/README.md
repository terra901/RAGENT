# storage

会话、认证、查询结果缓存、反馈元数据和 SQL 模板的存储模块。这里是基础设施层，控制器不直接拼接底层 SQL。

## 文件树

```text
storage/
├── auth_schema.py          # 用户、权限、会话和聊天表 DDL
├── auth_serializers.py     # 身份域行数据转换
├── auth_store.py           # MySQL 身份、权限和聊天仓储
├── feedback_bm25.py        # 反馈样本 BM25 召回
├── feedback_models.py      # 反馈样本数据结构
├── feedback_store.py       # 反馈 SQLite 元数据仓储
├── feedback_vector.py      # 反馈样本向量召回
├── redis.py                # Redis 会话和结果缓存
├── result_cache.py         # 进程内 SQL 结果缓存
├── sql_template_schema.py  # SQL 模板表 DDL
├── sql_template_store.py   # SQL 模板 MySQL 仓储
├── sql_template_writer.py  # 模板文件导出
└── stores.py               # 存储协议和内存实现
```
