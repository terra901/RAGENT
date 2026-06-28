"""OpenTelemetry 初始化。"""
from __future__ import annotations

from typing import Any

from ..core.logging import get_logger

log = get_logger(__name__)
_CONFIGURED = False


def configure_opentelemetry(settings: Any) -> None:
    """配置 OpenTelemetry tracer provider，缺依赖时自动降级。"""
    global _CONFIGURED
    if _CONFIGURED or not getattr(settings, "otel_enabled", True):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _CONFIGURED = True
        log.info("OpenTelemetry enabled: service=%s", settings.otel_service_name)
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenTelemetry init skipped: %s", exc)
