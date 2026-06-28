"""SQL 模板注册表导入写入函数。"""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import text


async def import_registry_rows(conn, registry: dict[str, Any], source_path: str = "") -> None:
    """导入完整注册表到 MySQL。"""
    now = time.time()
    await write_registry_meta(conn, registry, source_path, now)
    for item in registry.get("dimension_definitions", []):
        await write_dimension(conn, item, now)
    for item in registry.get("metric_definitions", []):
        await write_metric(conn, item, now)
    for item in registry.get("sql_templates", []):
        await write_template(conn, item, now)


async def write_registry_meta(conn, registry: dict[str, Any], source_path: str, now: float) -> None:
    """写入注册表元信息。"""
    await conn.execute(text(
        """
        INSERT INTO sql_template_registry_meta(registry_name, version, language, payload_json, source_path, updated_at)
        VALUES(:registry_name, :version, :language, CAST(:payload_json AS JSON), :source_path, :updated_at)
        ON DUPLICATE KEY UPDATE version=:version, language=:language,
          payload_json=CAST(:payload_json AS JSON), source_path=:source_path, updated_at=:updated_at
        """
    ), {
        "registry_name": registry.get("registry_name", "ragent_sql_template_registry"),
        "version": str(registry.get("version", "")),
        "language": str(registry.get("language", "")),
        "payload_json": json.dumps(registry, ensure_ascii=False),
        "source_path": source_path,
        "updated_at": now,
    })


async def write_dimension(conn, item: dict[str, Any], now: float) -> None:
    """写入维度定义。"""
    await conn.execute(text(
        """
        INSERT INTO sql_template_dimensions(dimension_id, name, semantic_type, description, query_guidance, payload_json, updated_at)
        VALUES(:dimension_id, :name, :semantic_type, :description, :query_guidance, CAST(:payload_json AS JSON), :updated_at)
        ON DUPLICATE KEY UPDATE name=:name, semantic_type=:semantic_type, description=:description,
          query_guidance=:query_guidance, payload_json=CAST(:payload_json AS JSON), updated_at=:updated_at
        """
    ), {
        "dimension_id": item["dimension_id"],
        "name": item.get("name", ""),
        "semantic_type": item.get("semantic_type"),
        "description": item.get("description", ""),
        "query_guidance": item.get("query_guidance", ""),
        "payload_json": json.dumps(item, ensure_ascii=False),
        "updated_at": now,
    })


async def write_metric(conn, item: dict[str, Any], now: float) -> None:
    """写入指标定义。"""
    await conn.execute(text(
        """
        INSERT INTO sql_template_metrics(metric_id, name, default_unit, aggregation, description,
          business_context, query_guidance, payload_json, updated_at)
        VALUES(:metric_id, :name, :default_unit, :aggregation, :description,
          :business_context, :query_guidance, CAST(:payload_json AS JSON), :updated_at)
        ON DUPLICATE KEY UPDATE name=:name, default_unit=:default_unit, aggregation=:aggregation,
          description=:description, business_context=:business_context, query_guidance=:query_guidance,
          payload_json=CAST(:payload_json AS JSON), updated_at=:updated_at
        """
    ), {
        "metric_id": item["metric_id"],
        "name": item.get("name", ""),
        "default_unit": item.get("default_unit"),
        "aggregation": item.get("aggregation"),
        "description": item.get("description", ""),
        "business_context": item.get("business_context", ""),
        "query_guidance": item.get("query_guidance", ""),
        "payload_json": json.dumps(item, ensure_ascii=False),
        "updated_at": now,
    })


async def write_template(conn, item: dict[str, Any], now: float) -> None:
    """写入 SQL 模板定义。"""
    params = template_params(item, now)
    await conn.execute(text(
        """
        INSERT INTO sql_templates(template_name, name, description, business_description,
          selection_guidance, slot_guidance, output_contract, compiler_guidance, priority, intent,
          source_tables_json, supported_metrics_json, supported_dimensions_json, analysis_types_json, payload_json, updated_at)
        VALUES(:template_name, :name, :description, :business_description, :selection_guidance,
          :slot_guidance, :output_contract, :compiler_guidance, :priority, :intent,
          CAST(:source_tables_json AS JSON), CAST(:supported_metrics_json AS JSON),
          CAST(:supported_dimensions_json AS JSON), CAST(:analysis_types_json AS JSON),
          CAST(:payload_json AS JSON), :updated_at)
        ON DUPLICATE KEY UPDATE name=:name, description=:description,
          business_description=:business_description, selection_guidance=:selection_guidance,
          slot_guidance=:slot_guidance, output_contract=:output_contract,
          compiler_guidance=:compiler_guidance, priority=:priority, intent=:intent,
          source_tables_json=CAST(:source_tables_json AS JSON),
          supported_metrics_json=CAST(:supported_metrics_json AS JSON),
          supported_dimensions_json=CAST(:supported_dimensions_json AS JSON),
          analysis_types_json=CAST(:analysis_types_json AS JSON),
          payload_json=CAST(:payload_json AS JSON), updated_at=:updated_at
        """
    ), params)


def template_params(item: dict[str, Any], now: float) -> dict[str, Any]:
    """生成模板写入参数。"""
    return {
        "template_name": item["template_name"],
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "business_description": item.get("business_description", ""),
        "selection_guidance": item.get("selection_guidance", ""),
        "slot_guidance": item.get("slot_guidance", ""),
        "output_contract": item.get("output_contract", ""),
        "compiler_guidance": item.get("compiler_guidance", ""),
        "priority": int(item.get("priority") or 0),
        "intent": item.get("intent", ""),
        "source_tables_json": json.dumps(item.get("source_tables", []), ensure_ascii=False),
        "supported_metrics_json": json.dumps(item.get("supported_metrics", []), ensure_ascii=False),
        "supported_dimensions_json": json.dumps(item.get("supported_dimensions", []), ensure_ascii=False),
        "analysis_types_json": json.dumps(item.get("analysis_types", []), ensure_ascii=False),
        "payload_json": json.dumps(item, ensure_ascii=False),
        "updated_at": now,
    }
