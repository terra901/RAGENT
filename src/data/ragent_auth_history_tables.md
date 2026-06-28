# RAGENT 用户认证与历史对话表

## 范围

这组表写入 MySQL `RAGENT` 库，用于前端登录注册、refresh token 会话和用户历史对话。

## 表

- `ragent_users`: 用户账号、密码哈希、状态和最后登录时间。
- `ragent_auth_sessions`: HttpOnly refresh token 的 SHA256 摘要和过期时间。
- `ragent_conversations`: 用户历史对话列表，删除操作采用归档标记。
- `ragent_conversation_messages`: 对话消息正文和结构化元数据，包括 SQL、结果行、图表和 trace ID。

## 认证流程

1. 注册或登录时，后端校验邮箱和密码。
2. 密码使用 `PBKDF2-HMAC-SHA256` 保存哈希，不保存明文。
3. 后端返回 HS256 access token，前端保存在 localStorage。
4. refresh token 写入 `HttpOnly` Cookie，数据库只保存 token 的 SHA256 摘要。
5. access token 过期时，前端调用 `/api/auth/refresh` 轮换 refresh token。
6. 退出登录时删除当前 refresh 会话并清理 Cookie。

## 历史对话流程

1. 登录后前端调用 `/api/conversations` 加载历史对话。
2. 提问前后端确认当前 `session_id` 属于当前用户，不存在时创建对话。
3. 用户消息和助手最终消息写入 `ragent_conversation_messages`。
4. 助手消息的 `metadata_json` 保存 SQL、rows、columns、steps、usage、chart_spec 和 trace_id。
5. 删除对话只把 `ragent_conversations.archived` 置为 `1`，不会物理删除消息。

## 当前行数

- `ragent_users`: 0 rows
- `ragent_auth_sessions`: 0 rows
- `ragent_conversations`: 0 rows
- `ragent_conversation_messages`: 0 rows

## SHOW CREATE TABLE

见同目录 `ragent_auth_history_show_create.sql`。
