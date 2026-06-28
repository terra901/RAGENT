# RAGENT Identity 与 Chat 表

## 业务边界

`RAGENT` 库中当前按两个应用业务边界落表：

- Identity: `users`, `auth_sessions`，负责注册、登录、账号状态、refresh token 会话。
- Chat: `chat_conversations`, `chat_messages`，负责用户历史聊天列表和消息增删查。

问数业务表和 SQL 模板元数据仍在同一个 MySQL schema 中，但 `users/auth_sessions/chat_*` 已加入后端 schema 排除列表，不进入自然语言问数的业务表召回。

## Identity 表

- `users`: 基于 Discord-bot 的 `rinsight_identity/users.sql` 结构，保留 `active/disabled/pending` 状态、邮箱唯一索引和管理员标记。
- `auth_sessions`: 保存 refresh token 的 SHA256 摘要，refresh token 明文只放 HttpOnly Cookie。

## Chat 表

- `chat_conversations`: 用户聊天会话列表，支持创建、重命名、查询、软删除。
- `chat_messages`: 聊天消息明细，保存用户消息、助手回答、SQL、结果行、图表、trace 等元数据。

## 当前行数

- `users`: 0 rows
- `auth_sessions`: 0 rows
- `chat_conversations`: 0 rows
- `chat_messages`: 0 rows

## SHOW CREATE TABLE

见同目录 `ragent_identity_chat_show_create.sql`。
