"""FastAPI lifespan 依赖装配。"""
from __future__ import annotations

from pathlib import Path

from ..connectors import make_connector
from ..core.config import settings
from ..core.logging import get_logger
from ..query_engine.schema_manager import SchemaManager
from ..query_engine.semantic_layer import SemanticLayer
from ..services import RuntimeDependencies, build_runtime

log = get_logger(__name__)


def backend_root() -> Path:
    """返回后端根目录。"""
    return Path(__file__).resolve().parents[2]


async def build_app_state() -> dict:
    """初始化应用级依赖并返回 state 字典。"""
    from ..core.migrations import migrate_db_layout

    migrate_db_layout(settings)
    connector = make_connector(settings.db_url, read_only=settings.db_read_only)
    semantic = load_semantic_layer()
    embedding_provider = warmup_embeddings()
    schema_manager = SchemaManager(connector=connector, semantic_layer=semantic, embedding_provider=embedding_provider)
    redis_client, session_store, result_cache = await build_cache_stores()
    feedback_store = build_feedback_store(embedding_provider)
    sql_template_store = await build_sql_template_store()
    auth_store = await init_store("AuthStore", lambda: __import_store("auth"))
    await ensure_bootstrap_admin(auth_store)
    model_repo = await init_store("ModelManagementRepository", lambda: __import_store("model"))
    job_store = await init_store("AgentJobStore", lambda: __import_store("job"))
    trace_store, tracer, callbacks = await build_tracing(semantic)
    llm, memory_provider = await build_llm_and_memory(callbacks, session_store, embedding_provider, redis_client)
    runtime = build_runtime(RuntimeDependencies(
        connector=connector,
        schema_manager=schema_manager,
        llm=llm,
        result_cache=result_cache,
        session_store=session_store,
        feedback_store=feedback_store,
        sql_template_store=sql_template_store,
        memory_provider=memory_provider,
        settings=settings,
    ))
    await runtime.initialize()
    return {
        "runtime": runtime,
        "memory": memory_provider,
        "redis_client": redis_client,
        "tracer": tracer,
        "auth_store": auth_store,
        "model_repo": model_repo,
        "job_store": job_store,
        "trace_store": trace_store,
        "feedback_store": feedback_store,
        "sql_template_store": sql_template_store,
    }


def load_semantic_layer():
    """加载 semantic_layer.json。"""
    path = backend_root() / "semantic_layer.json"
    if not path.exists():
        return None
    try:
        semantic = SemanticLayer.from_json(path)
        log.info("Loaded semantic layer: %d mappings", len(semantic.mappings))
        return semantic
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to load semantic_layer.json: %s", exc)
        return None


def warmup_embeddings():
    """按配置初始化 embedding provider。"""
    if not settings.embeddings_enabled:
        return None
    from ..retrieval.embeddings import get_default_provider

    provider = get_default_provider()
    if provider is None:
        log.warning("Embeddings enabled but provider init failed")
        return None
    try:
        provider.encode(["warmup"])
    except Exception as exc:  # noqa: BLE001
        log.warning("Embedding warmup failed: %s", exc)
    return provider


async def build_cache_stores():
    """构造 Redis 或内存缓存/会话存储。"""
    if settings.redis_url:
        try:
            from ..storage.redis import RedisResultCache, RedisSessionStore, make_redis_client

            client = await make_redis_client(settings.redis_url)
            return (
                client,
                RedisSessionStore(client, prefix=settings.redis_key_prefix, ttl_seconds=settings.session_ttl_seconds),
                RedisResultCache(client, prefix=settings.redis_key_prefix, ttl_seconds=settings.result_cache_ttl_seconds),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Redis init failed; using in-memory stores: %s", exc)
    from ..storage.stores import InMemoryResultCache, InMemorySessionStore

    return (
        None,
        InMemorySessionStore(max_count=settings.session_max_count, ttl_seconds=settings.session_ttl_seconds),
        InMemoryResultCache(ttl_seconds=settings.result_cache_ttl_seconds, max_size=settings.result_cache_max_size),
    )


def build_feedback_store(embedding_provider):
    """构造反馈 few-shot 仓储。"""
    if not settings.feedback_enabled:
        return None
    try:
        from ..storage.feedback_store import FeedbackStore

        return FeedbackStore(
            db_path=settings.feedback_db_path,
            recall_top_k=settings.feedback_recall_top_k,
            vec_db_path=settings.vec_db_path if settings.rag_enabled else None,
            embedding_provider=embedding_provider,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("FeedbackStore init failed: %s", exc)
        return None


async def build_sql_template_store():
    """构造并导入 SQL 模板仓储。"""
    if not settings.sql_template_enabled:
        return None
    try:
        from ..storage.sql_template_store import SqlTemplateStore

        store = SqlTemplateStore(database_url=settings.db_url)
        await store.initialize()
        path = Path(settings.sql_template_registry_path)
        path = path if path.is_absolute() else backend_root() / path
        if path.exists():
            await store.import_registry_file(path)
        return store
    except Exception as exc:  # noqa: BLE001
        log.error("SqlTemplateStore init failed: %s", exc)
        return None


async def init_store(name: str, factory):
    """初始化一个带 initialize 方法的仓储。"""
    try:
        store = factory()
        await store.initialize()
        return store
    except Exception as exc:  # noqa: BLE001
        log.error("%s init failed: %s", name, exc)
        return None


async def ensure_bootstrap_admin(auth_store) -> None:
    """按配置创建或修复启动管理员账号。"""
    if auth_store is None or not settings.bootstrap_admin_enabled:
        return
    try:
        from ..core.auth import hash_password, normalize_email

        modules = [item.strip() for item in settings.bootstrap_admin_modules.split(",") if item.strip()]
        await auth_store.ensure_admin_user(
            email=normalize_email(settings.bootstrap_admin_email),
            password_hash=hash_password(settings.bootstrap_admin_password),
            name=settings.bootstrap_admin_name,
            allowed_modules=modules,
        )
        log.info("Bootstrap admin ensured: %s", settings.bootstrap_admin_email)
    except Exception as exc:  # noqa: BLE001
        log.error("Bootstrap admin init failed: %s", exc)


def __import_store(kind: str):
    """延迟导入仓储，避免启动期循环依赖。"""
    if kind == "auth":
        from ..storage.auth_store import AuthStore
        return AuthStore(database_url=settings.db_url)
    if kind == "model":
        from ..admin.model_repository import ModelManagementRepository
        return ModelManagementRepository(database_url=settings.db_url)
    from ..runtime.job_store import AgentJobStore
    return AgentJobStore(database_url=settings.db_url)


async def build_tracing(semantic):
    """初始化 trace store、OpenTelemetry 和 LangChain callbacks。"""
    if not settings.tracing_enabled:
        return None, None, []
    try:
        from ..observability.decorators import set_sensitive_columns
        from ..observability.otel import configure_opentelemetry
        from ..observability.trace_store import TraceStore
        from ..observability.tracer import LangChainTracer, Tracer, set_current_tracer

        store = TraceStore(db_path=settings.trace_db_path)
        await store.start()
        await store.cleanup(retention_days=settings.trace_retention_days)
        tracer = Tracer(store=store, sample_rate=settings.trace_sample_rate)
        configure_opentelemetry(settings)
        set_current_tracer(tracer)
        if semantic is not None and getattr(semantic, "sensitive_columns", None):
            set_sensitive_columns(list(semantic.sensitive_columns.keys()))
        return store, tracer, [LangChainTracer()]
    except Exception as exc:  # noqa: BLE001
        log.error("Tracing init failed; tracing disabled: %s", exc)
        return None, None, []


async def build_llm_and_memory(callbacks, session_store, embedding_provider, redis_client):
    """构造主 LLM 和记忆 Provider。"""
    from ..llm.provider import build_llm
    from ..memory import make_memory_provider

    llm = build_llm(callbacks=callbacks)
    summary_llm = llm
    if settings.memory_summary_llm_model:
        try:
            summary_llm = build_llm(model=settings.memory_summary_llm_model)
        except Exception as exc:  # noqa: BLE001
            log.warning("summary_llm build failed: %s; falling back to primary LLM", exc)
    memory = make_memory_provider(
        session_store=session_store,
        embedding_provider=embedding_provider,
        summary_llm=summary_llm,
        redis_client=redis_client,
    )
    return llm, memory


async def cleanup_app_state(state: dict) -> None:
    """按依赖类型释放应用状态。"""
    runtime = state.get("runtime")
    if runtime is not None:
        await runtime.shutdown()
    memory = state.get("memory")
    if memory is not None:
        closer = getattr(memory, "close", None)
        if closer:
            result = closer()
            if hasattr(result, "__await__"):
                await result
    redis_client = state.get("redis_client")
    if redis_client is not None:
        await redis_client.aclose()
    for key in ("feedback_store", "sql_template_store", "auth_store", "model_repo", "job_store", "trace_store"):
        item = state.get(key)
        if item is None:
            continue
        closer = getattr(item, "close", None) or getattr(item, "stop", None)
        if closer:
            result = closer()
            if hasattr(result, "__await__"):
                await result
