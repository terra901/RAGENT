"""SQL 模板注册表 DDL。"""
from __future__ import annotations

SQL_TEMPLATE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS sql_template_registry_meta (
        registry_name VARCHAR(128) PRIMARY KEY,
        version VARCHAR(64) NOT NULL,
        language VARCHAR(32) NOT NULL,
        payload_json JSON NOT NULL,
        source_path VARCHAR(1024),
        updated_at DOUBLE NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    COMMENT='SQL 模板注册表元信息'
    """,
    """
    CREATE TABLE IF NOT EXISTS sql_template_dimensions (
        dimension_id VARCHAR(128) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        semantic_type VARCHAR(64),
        description TEXT,
        query_guidance TEXT,
        payload_json JSON NOT NULL,
        updated_at DOUBLE NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    COMMENT='SQL 模板维度定义'
    """,
    """
    CREATE TABLE IF NOT EXISTS sql_template_metrics (
        metric_id VARCHAR(128) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        default_unit VARCHAR(64),
        aggregation VARCHAR(64),
        description TEXT,
        business_context TEXT,
        query_guidance TEXT,
        payload_json JSON NOT NULL,
        updated_at DOUBLE NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    COMMENT='SQL 模板指标定义'
    """,
    """
    CREATE TABLE IF NOT EXISTS sql_templates (
        template_name VARCHAR(128) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        business_description TEXT,
        selection_guidance TEXT,
        slot_guidance TEXT,
        output_contract TEXT,
        compiler_guidance TEXT,
        priority INT NOT NULL DEFAULT 0,
        intent VARCHAR(128),
        source_tables_json JSON NOT NULL,
        supported_metrics_json JSON NOT NULL,
        supported_dimensions_json JSON NOT NULL,
        analysis_types_json JSON NOT NULL,
        payload_json JSON NOT NULL,
        updated_at DOUBLE NOT NULL,
        KEY idx_sql_templates_priority (priority),
        KEY idx_sql_templates_intent (intent)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    COMMENT='SQL 查询模板定义'
    """,
]
