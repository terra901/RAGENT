"""运行时工厂，提供基于导入路径的扩展点。"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel

from ..core.config import Settings
from ..connectors.base import BaseConnector
from ..core.logging import get_logger
from ..memory import MemoryProvider
from ..query_engine.schema_manager import SchemaManager
from ..storage.stores import ResultCacheStore, SessionStore
from .agent_port import AgentRuntime
from .basic_query_service import BasicQueryService

log = get_logger(__name__)


@dataclass
class RuntimeDependencies:
    """传给运行时工厂的依赖集合。"""

    connector: BaseConnector
    schema_manager: SchemaManager
    llm: BaseChatModel
    result_cache: ResultCacheStore
    session_store: SessionStore
    memory_provider: MemoryProvider
    settings: Settings
    feedback_store: Any | None = None
    sql_template_store: Any | None = None


def _load_factory(path: str):
    """从 `module:function` 字符串加载运行时工厂函数。"""
    if ":" not in path:
        raise ValueError("DA_AGENT_RUNTIME_FACTORY 必须使用 'module:function' 格式")
    module_name, attr_name = path.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name)
    if not callable(factory):
        raise TypeError(f"{path!r} 不是可调用对象")
    return factory


def build_runtime(deps: RuntimeDependencies) -> AgentRuntime:
    """创建当前启用的运行时。

    默认运行时是 `BasicQueryService`。后续如果要接入 agent 图编排，
    只需要把 `DA_AGENT_RUNTIME_FACTORY` 配置成一个导入路径；
    该路径指向的函数接收 `RuntimeDependencies` 并返回 `AgentRuntime`。
    """
    factory_path = deps.settings.agent_runtime_factory.strip()
    if not factory_path:
        return BasicQueryService(
            connector=deps.connector,
            schema_manager=deps.schema_manager,
            llm=deps.llm,
            result_cache=deps.result_cache,
            session_store=deps.session_store,
            feedback_store=deps.feedback_store,
            sql_template_store=deps.sql_template_store,
            memory_provider=deps.memory_provider,
        )

    factory = _load_factory(factory_path)
    runtime = factory(deps)
    if not isinstance(runtime, AgentRuntime):
        raise TypeError(
            "自定义运行时必须实现 data_agent.services.AgentRuntime"
        )
    log.info("已加载自定义运行时工厂: %s", factory_path)
    return runtime
