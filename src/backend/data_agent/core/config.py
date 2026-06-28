"""应用配置，通过环境变量和 .env 文件管理。"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_AUTH_MODULES = (
    "chat",
    "data_query",
    "schema",
    "sql_template",
    "chart",
    "trace",
    "feedback",
    "memory",
)


class Settings(BaseSettings):
    """保存后端运行配置，并从环境变量加载覆盖值。"""
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="DA_",
    )

    # ---- LLM ----
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2048

    # ---- DB ----
    db_url: str = "mysql+asyncmy://root:140617@127.0.0.1:3306/RAGENT?charset=utf8mb4"
    db_read_only: bool = True

    # ---- 安全 ----
    safety_max_rows: int = 100
    safety_query_timeout: float = 30.0
    safety_max_tokens_per_request: int = 0

    # ---- 列级保护 / 数据脱敏 ----
    # off    : 不处理
    # mask   : 结果后置脱敏（13*****1234 等）
    # reject : 检测到 SQL 引用敏感列即拒绝执行
    masking_mode: str = "mask"

    # ---- 服务 ----
    host: str = "0.0.0.0"
    port: int = 8000

    # ---- CORS（逗号分隔；为空时根据环境推断）----
    cors_origins: str = ""
    cors_allow_credentials: bool = False

    # ---- 限流（每分钟最大请求数；0 = 关闭）----
    rate_limit_per_minute: int = 60

    # ---- API Key 认证（可选；为空时不开启）----
    api_key: str = ""

    # ---- 用户认证 ----
    jwt_secret: str = "ragent-local-dev-secret-change-me"
    jwt_issuer: str = "ragent-data-agent"
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 7 * 24 * 3600
    auth_cookie_secure: bool = False
    default_allowed_modules: str = ",".join(DEFAULT_AUTH_MODULES)
    bootstrap_admin_enabled: bool = True
    bootstrap_admin_email: str = "admin@ragent.local"
    bootstrap_admin_password: str = "140617"
    bootstrap_admin_name: str = "RAGENT 管理员"
    bootstrap_admin_modules: str = ",".join((*DEFAULT_AUTH_MODULES, "admin", "model_management", "observability", "queue"))

    # ---- 日志 ----
    log_level: str = "INFO"

    # ---- 会话 ----
    session_ttl_seconds: int = 3600
    session_max_count: int = 1000
    session_history_turns: int = 3

    # ---- Schema 召回 / 启动期 ----
    schema_recall_threshold: int = 8
    schema_recall_top_k: int = 8
    schema_with_count: bool = True
    schema_excluded_tables: str = (
        "users,"
        "auth_sessions,"
        "user_permissions,"
        "chat_conversations,"
        "chat_messages,"
        "ragent_users,"
        "ragent_auth_sessions,"
        "ragent_conversations,"
        "ragent_conversation_messages,"
        "sql_template_registry_meta,"
        "sql_template_dimensions,"
        "sql_template_metrics,"
        "sql_templates"
    )

    # ---- /api/health 详情 ----
    health_verbose: bool = True

    # ---- 图表规格（Vega-Lite）----
    chart_enabled: bool = True
    chart_min_rows: int = 2
    chart_max_rows: int = 200

    # ---- 结果缓存（同 SQL + 同库 → 缓存命中跳过 DB） ----
    result_cache_ttl_seconds: int = 300
    result_cache_max_size: int = 200

    # ---- Embedding 召回（fastembed） ----
    embeddings_enabled: bool = False
    embeddings_model: str = "BAAI/bge-small-zh-v1.5"

    # ---- LLM Token 流式输出（SSE sql_chunk / answer_chunk） ----
    stream_llm_tokens: bool = True

    # ---- 自学习 Few-shot 反馈 ----
    feedback_enabled: bool = True
    feedback_db_path: str = "./data/feedback.db"
    feedback_auto_approve: bool = False
    feedback_recall_top_k: int = 3

    # ---- SQL 模板注册表 ----
    sql_template_enabled: bool = True
    sql_template_registry_path: str = "./data_agent/sql_template/ragent_sql_template_registry.json"

    # ---- Redis 持久化（留空时全部用进程内存）----
    redis_url: str = ""
    redis_key_prefix: str = "data-agent"

    # ---- Agent runtime 接入预留 ----
    agent_runtime_factory: str = ""

    # ---- RAG / 检索（Phase 2） ----
    rag_enabled: bool = True
    vec_db_path: str = "./data/memory.db"
    rag_fusion_weights: str = "0.4,0.4,0.2"

    # ---- Memory（Phase 2） ----
    memory_enabled: bool = True
    memory_summary_llm_model: str = ""
    memory_summary_max_chars: int = 200
    memory_semantic_top_k: int = 3
    memory_semantic_min_turns: int = 4
    memory_semantic_threshold: float = 0.55
    memory_semantic_overfetch_factor: int = 5
    memory_semantic_overfetch_min: int = 20

    # ---- Tracing / Observability ----
    tracing_enabled: bool = True
    trace_db_path: str = "./data/trace.db"
    trace_retention_days: int = 7
    trace_sample_rate: float = 1.0
    trace_api_enabled: bool = False
    otel_enabled: bool = True
    otel_service_name: str = "ragent-agent"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://127.0.0.1:3000"
    langfuse_environment: str = "local"

    # ---- Model 管理 ----
    model_key_secret: str = "ragent-model-key-secret-140617"

    # ---- RabbitMQ / Celery ----
    rabbitmq_url: str = "amqp://ragent:140617@127.0.0.1:5673/ragent"
    celery_broker_url: str = "amqp://ragent:140617@127.0.0.1:5673/ragent"
    celery_result_backend: str = ""
    timezone: str = "Asia/Shanghai"

    def rag_fusion_weights_tuple(self) -> tuple[float, ...]:
        """把 '0.4,0.4,0.2' 解析为 tuple；非法值回退到 (0.4, 0.4, 0.2)。"""
        try:
            parts = tuple(float(x.strip()) for x in self.rag_fusion_weights.split(",") if x.strip())
            return parts or (0.4, 0.4, 0.2)
        except ValueError:
            return (0.4, 0.4, 0.2)

    def cors_origins_list(self) -> list[str]:
        """把逗号分隔的 CORS 配置解析为列表；为空时仅允许本机。"""
        if not self.cors_origins.strip():
            return ["http://127.0.0.1:8000", "http://localhost:8000"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def schema_excluded_table_set(self) -> set[str]:
        """Return tables that should not enter business schema recall."""
        return {t.strip() for t in self.schema_excluded_tables.split(",") if t.strip()}


settings = Settings()
