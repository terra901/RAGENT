"""@traced 装饰器：自动为 async / sync 函数生成 span。

敏感列脱敏说明：递归扫描 dict / list / tuple 所有键，命中 _SENSITIVE_COLS 即把值
（连同嵌套结构）替换为 "***"。`set_sensitive_columns` 入参做归一化（去前缀 `users.`
/ `*.`），以匹配函数参数名 / 结果字段名。
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import time
from typing import Any, Callable

from .tracer import _safe_json, current_span_id, current_trace_id, get_current_tracer
from .models import Span

_SENSITIVE_COLS: set[str] = set()
_BIG_OBJ_SUMMARY_KEYS = {
    "QueryResult": ("columns", "row_count", "execution_time_ms"),
}


def set_sensitive_columns(cols: list[str]) -> None:
    """启动期由 lifespan 调用，注入敏感列名集合。

    入参格式见 `semantic_layer.json.sensitive_columns`：
      - "users.phone" -> 抽出 "phone"
      - "*.email"     -> 抽出 "email"
      - "password"    -> 原样保留

    所有 key 小写化，去掉表前缀（`<table>.<col>` 取后半段）和通配符前缀（`*.`）。
    """
    global _SENSITIVE_COLS
    normalized: set[str] = set()
    for c in cols:
        if not c:
            continue
        s = c.lower()
        if s.startswith("*."):
            s = s[2:]
        elif "." in s:
            s = s.split(".", 1)[1]
        if s:
            normalized.add(s)
    _SENSITIVE_COLS = normalized


def _is_sensitive(key: str) -> bool:
    """执行 is_sensitive 逻辑。"""
    return isinstance(key, str) and key.lower() in _SENSITIVE_COLS


def _mask_recursive(value: Any) -> Any:
    """递归地把命中敏感列的字段值替换为 ***。

    - dict：遍历每个 (k, v)，命中 _SENSITIVE_COLS 时 v 整体替换为 ***，否则继续递归 v
    - list / tuple：递归 each item（保持容器类型）
    - 其他类型：原样返回
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _is_sensitive(k):
                out[k] = "***"
            else:
                out[k] = _mask_recursive(v)
        return out
    if isinstance(value, list):
        return [_mask_recursive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_recursive(item) for item in value)
    return value


def _serialize_arg(name: str, value: Any) -> Any:
    """单个函数参数 → trace JSON value。

    - 参数名命中敏感列 → 整体替换 ***
    - 大对象（QueryResult）→ 仅摘要关键字段（columns/row_count/time）
    - 其他容器 → 递归脱敏
    """
    if _is_sensitive(name):
        return "***"
    cls_name = type(value).__name__
    if cls_name in _BIG_OBJ_SUMMARY_KEYS:
        return {k: getattr(value, k, None) for k in _BIG_OBJ_SUMMARY_KEYS[cls_name]}
    return _mask_recursive(value)


def _filter_inputs(func: Callable, args: tuple, kwargs: dict) -> dict:
    """执行 filter_inputs 逻辑。"""
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        out = {}
        for k, v in bound.arguments.items():
            if k in ("self", "cls"):
                continue
            try:
                out[k] = _serialize_arg(k, v)
            except Exception:  # noqa: BLE001
                out[k] = repr(v)[:200]
        return out
    except Exception:  # noqa: BLE001
        return {}


def _filter_outputs(result: Any) -> Any:
    """执行 filter_outputs 逻辑。"""
    cls_name = type(result).__name__
    if cls_name in _BIG_OBJ_SUMMARY_KEYS:
        return {k: getattr(result, k, None) for k in _BIG_OBJ_SUMMARY_KEYS[cls_name]}
    return _mask_recursive(result)


def traced(name: str | None = None, kind: str = "chain", capture_io: bool = True):
    """装饰 async / sync 函数，自动生成 span。

    sync 函数：测时（time.perf_counter）+ 通过 tracer._store fire-and-forget 写入；
    span 没有 await 点也能落库，但无法捕获深层 ContextVar 变更（与 async 等价对外）。
    """

    def decorator(func: Callable) -> Callable:
        """执行 decorator 逻辑。"""
        span_name = name or func.__name__
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                """异步执行 async_wrapper 逻辑。"""
                tracer = get_current_tracer()
                if tracer is None:
                    return await func(*args, **kwargs)
                inputs = _filter_inputs(func, args, kwargs) if capture_io else None
                async with tracer.span(name=span_name, kind=kind, inputs=inputs) as sp:
                    result = await func(*args, **kwargs)
                    if capture_io:
                        sp.set_output(_filter_outputs(result))
                    return result
            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            """执行 sync_wrapper 逻辑。"""
            tracer = get_current_tracer()
            tid = current_trace_id.get()
            if tracer is None or not tid:
                return func(*args, **kwargs)
            import uuid
            parent = current_span_id.get() or None
            sp = Span(
                span_id=uuid.uuid4().hex,
                trace_id=tid,
                parent_span_id=parent,
                name=span_name,
                kind=kind,
                started_at=time.time(),
                inputs_json=(
                    _safe_json(_filter_inputs(func, args, kwargs)) if capture_io else None
                ),
            )
            err_str: str | None = None
            try:
                result = func(*args, **kwargs)
                if capture_io:
                    sp.outputs_json = _safe_json(_filter_outputs(result))
                return result
            except BaseException as e:  # noqa: BLE001
                err_str = repr(e)[:500]
                raise
            finally:
                sp.ended_at = time.time()
                sp.error = err_str
                # 同步路径：用 fire-and-forget 入队（write_span 是 async；调度到当前 loop）
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(tracer._store.write_span(sp))
                except RuntimeError:
                    # 无运行 loop（罕见，比如 atexit 阶段）；丢弃以避免错传
                    pass

        return sync_wrapper

    return decorator
