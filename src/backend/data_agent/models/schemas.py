"""HTTP API 的 Pydantic 模型定义。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuthRegisterRequest(BaseModel):
    """注册请求体。"""

    name: str = Field(..., min_length=1, max_length=80)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class AuthLoginRequest(BaseModel):
    """登录请求体。"""

    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class AuthUserResponse(BaseModel):
    """返回给浏览器的用户字段。"""

    id: str
    email: str
    name: str
    status: str
    is_admin: bool = False
    last_login_at: str | None = None


class AuthPermissionsResponse(BaseModel):
    """返回给浏览器的权限字段。"""

    can_create_template: bool = True
    can_update_own_template: bool = True
    can_delete_own_template: bool = True
    can_view_public_template: bool = True
    can_publish_template: bool = False
    can_import_template: bool = True
    can_export_template: bool = True
    can_manage_users: bool = False
    can_manage_permissions: bool = False
    allowed_modules: list[str] = Field(default_factory=list)


class AuthResponse(BaseModel):
    """登录、注册和刷新返回体。"""

    access_token: str
    expires_in: int
    token_type: str = "Bearer"
    rotated: bool = False
    user: AuthUserResponse
    permissions: AuthPermissionsResponse


class ConversationCreateRequest(BaseModel):
    """创建对话请求。"""

    title: str | None = Field(default=None, max_length=255)


class ConversationUpdateRequest(BaseModel):
    """更新对话请求。"""

    title: str = Field(..., min_length=1, max_length=255)


class AskRequest(BaseModel):
    """同步和流式问答请求体。"""

    question: str = Field(..., min_length=1, max_length=2000, description="自然语言问题")
    session_id: str = Field(default="default", description="会话 ID，用于多轮对话")


class StepResponse(BaseModel):
    """展示给前端的一步处理状态。"""

    name: str
    status: str
    detail: str = ""
    elapsed_ms: float = 0.0


class UsageResponse(BaseModel):
    """当前运行时返回的 token 用量。"""

    model_config = {"protected_namespaces": ()}
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_calls: int = 0


class AskResponse(BaseModel):
    """同步问答接口完整返回体。"""

    answer: str
    sql: str | None = None
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    row_count: int = 0
    execution_time_ms: float = 0
    visualization_hint: str | None = None
    chart_spec: dict[str, Any] | None = None
    steps: list[StepResponse] = Field(default_factory=list)
    total_usage: UsageResponse = Field(default_factory=UsageResponse)
    cache_hit: bool = False
    memory_used: bool = False
    trace_id: str | None = None
    thread_id: str | None = None


class HealthResponse(BaseModel):
    """健康检查返回体。"""

    status: str
    runtime: str = ""
    resume_supported: bool = False
    tables: list[str] = Field(default_factory=list)
    llm_model: str = ""
    llm_base_url: str = ""
    cache_stats: dict[str, int] = Field(default_factory=dict)
    table_count: int = 0


class SchemaColumnResp(BaseModel):
    """表字段描述。"""

    name: str
    data_type: str
    nullable: bool = True
    comment: str | None = None
    is_primary_key: bool = False


class SchemaTableResp(BaseModel):
    """表描述。"""

    name: str
    comment: str | None = None
    row_count: int | None = None
    columns: list[SchemaColumnResp]


class SchemaResp(BaseModel):
    """Schema 接口返回体。"""

    tables: list[SchemaTableResp]


class ResumeRequest(BaseModel):
    """保留给 agent/HIL 的 resume 请求体。"""

    thread_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=64)
    user_input: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    """新增用户反馈请求体。"""

    question: str = Field(..., min_length=1, max_length=2000)
    sql: str = Field(..., min_length=1, max_length=8000)
    status: str = Field(default="pending", pattern="^(pending|approved|rejected)$")
    note: str | None = None


class FeedbackEntryResp(BaseModel):
    """反馈条目返回体。"""

    id: int
    question: str
    sql: str
    status: str
    note: str | None = None
    created_at: float
    updated_at: float


class SqlTemplateSummaryResp(BaseModel):
    """SQL 模板摘要。"""

    template_name: str
    name: str
    description: str = ""
    business_description: str = ""
    selection_guidance: str = ""
    priority: int = 0
    intent: str = ""
    source_tables: list[str] = Field(default_factory=list)
    supported_metrics: list[str] = Field(default_factory=list)
    supported_dimensions: list[str] = Field(default_factory=list)
    analysis_types: list[str] = Field(default_factory=list)
