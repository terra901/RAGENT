# RAGENTv2 Frontend

Vue 3 ESM 静态前端，由后端 FastAPI 挂载到 `/ui/`。

- 无需 Vite/Node 构建。
- API 默认调用同源 `/api/*`。
- 登录注册入口为 `/api/auth/*`。
- 历史对话入口为 `/api/conversations/*`。
- SSE RAGENT 入口为 `POST /api/ask/stream`。
- 左侧管理员入口由当前用户的 `is_admin` 控制。
- 输入框上方的排队提示轮询 `/api/jobs/queue`。
- 后台管理页面位于 `admin/`，目前包含模型管理和 trace 可观测页面。

当前界面不展示数据库 schema。schema 仍由后端提供给 RAGENT runtime 使用。
