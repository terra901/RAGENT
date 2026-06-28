"""模型管理 MySQL 仓储。"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..core.config import settings
from .model_crypto import ModelKeyCipher, mask_api_key
from .model_payloads import model_to_dict, nullable_int, provider_to_dict


MODEL_MANAGEMENT_DDL = [
    """
    CREATE TABLE IF NOT EXISTS model_providers (
      id CHAR(36) NOT NULL,
      name VARCHAR(128) NOT NULL,
      code VARCHAR(128) NOT NULL,
      base_url VARCHAR(512) NOT NULL,
      api_type VARCHAR(64) NOT NULL DEFAULT 'openai_compatible',
      status ENUM('active','disabled') NOT NULL DEFAULT 'active',
      timeout_seconds INT NOT NULL DEFAULT 60,
      max_retries INT NOT NULL DEFAULT 2,
      remark VARCHAR(512) DEFAULT NULL,
      created_by CHAR(36) DEFAULT NULL,
      updated_by CHAR(36) DEFAULT NULL,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      UNIQUE KEY uk_model_providers_code (code),
      KEY idx_model_providers_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT 模型供应商表'
    """,
    """
    CREATE TABLE IF NOT EXISTS models (
      id CHAR(36) NOT NULL,
      provider_id CHAR(36) NOT NULL,
      model_name VARCHAR(255) NOT NULL,
      display_name VARCHAR(255) NOT NULL,
      model_type VARCHAR(64) NOT NULL,
      usage_position VARCHAR(128) NOT NULL DEFAULT '',
      encrypted_key TEXT NULL,
      key_mask VARCHAR(64) NULL,
      context_window INT DEFAULT NULL,
      last_test_status ENUM('success','failed','unknown') NOT NULL DEFAULT 'unknown',
      last_test_message VARCHAR(512) DEFAULT NULL,
      last_test_at DATETIME(3) DEFAULT NULL,
      status ENUM('active','disabled') NOT NULL DEFAULT 'active',
      remark VARCHAR(512) DEFAULT NULL,
      created_by CHAR(36) DEFAULT NULL,
      updated_by CHAR(36) DEFAULT NULL,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      KEY idx_models_provider_usage_status (provider_id, usage_position, status),
      CONSTRAINT fk_models_provider_id FOREIGN KEY (provider_id) REFERENCES model_providers(id)
        ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT 模型表：每个模型保存唯一当前 Key'
    """,
]


class ModelManagementRepository:
    """模型管理库访问层。"""

    def __init__(self, database_url: str | None = None) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url or settings.db_url, echo=False, pool_pre_ping=True)
        self.cipher = ModelKeyCipher(settings.model_key_secret)

    async def initialize(self) -> None:
        """创建模型管理表。"""
        async with self._engine.begin() as conn:
            for ddl in MODEL_MANAGEMENT_DDL:
                await conn.execute(text(ddl))

    async def close(self) -> None:
        """释放连接池。"""
        await self._engine.dispose()

    async def list_providers(self) -> list[dict[str, Any]]:
        """查询供应商列表。"""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(
                """
                SELECT p.*, COUNT(m.id) AS model_count
                FROM model_providers p LEFT JOIN models m ON m.provider_id = p.id
                GROUP BY p.id ORDER BY p.created_at ASC, p.name ASC
                """
            ))).mappings().all()
        return [provider_to_dict(dict(row)) for row in rows]

    async def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        """按 ID 查询供应商。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(
                """
                SELECT p.*, COUNT(m.id) AS model_count
                FROM model_providers p LEFT JOIN models m ON m.provider_id = p.id
                WHERE p.id=:id GROUP BY p.id LIMIT 1
                """
            ), {"id": provider_id})).mappings().first()
        return provider_to_dict(dict(row)) if row else None

    async def create_provider(self, payload: dict[str, Any], user_id: str | None) -> dict[str, Any]:
        """创建供应商。"""
        provider_id = str(uuid.uuid4())
        async with self._engine.begin() as conn:
            await conn.execute(text(
                """
                INSERT INTO model_providers(
                  id, name, code, base_url, api_type, status, timeout_seconds, max_retries, remark, created_by, updated_by
                ) VALUES(:id,:name,:code,:base_url,:api_type,:status,:timeout_seconds,:max_retries,:remark,:created_by,:updated_by)
                """
            ), {**payload, "id": provider_id, "created_by": user_id, "updated_by": user_id})
        return await self.get_provider(provider_id) or {}

    async def update_provider(self, provider_id: str, payload: dict[str, Any], user_id: str | None) -> dict[str, Any]:
        """更新供应商。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(text(
                """
                UPDATE model_providers
                SET name=:name, code=:code, base_url=:base_url, api_type=:api_type, status=:status,
                    timeout_seconds=:timeout_seconds, max_retries=:max_retries, remark=:remark, updated_by=:updated_by
                WHERE id=:id
                """
            ), {**payload, "id": provider_id, "updated_by": user_id})
            if not result.rowcount:
                raise ValueError("供应商不存在。")
        return await self.get_provider(provider_id) or {}

    async def delete_provider(self, provider_id: str) -> None:
        """删除供应商及其模型。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(text("DELETE FROM model_providers WHERE id=:id"), {"id": provider_id})
            if not result.rowcount:
                raise ValueError("供应商不存在。")

    async def list_models(self, provider_id: str) -> list[dict[str, Any]]:
        """查询供应商下的模型。"""
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT * FROM models WHERE provider_id=:provider_id ORDER BY created_at ASC, display_name ASC"),
                {"provider_id": provider_id},
            )).mappings().all()
        return [model_to_dict(dict(row)) for row in rows]

    async def get_model_with_provider(self, model_id: str) -> dict[str, Any] | None:
        """查询模型及供应商连接配置。"""
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(
                """
                SELECT m.*, p.base_url, p.api_type, p.timeout_seconds
                FROM models m JOIN model_providers p ON p.id = m.provider_id
                WHERE m.id=:id LIMIT 1
                """
            ), {"id": model_id})).mappings().first()
        if not row:
            return None
        data = dict(row)
        model = model_to_dict(data)
        model.update(baseUrl=data["base_url"], apiType=data["api_type"], timeoutSeconds=data["timeout_seconds"])
        model["apiKey"] = self.cipher.decrypt(data.get("encrypted_key"))
        return model

    def key_values(self, api_key: str | None) -> tuple[str | None, str | None]:
        """生成数据库保存的加密 Key 和脱敏 Key。"""
        raw = str(api_key or "").strip()
        return (self.cipher.encrypt(raw), mask_api_key(raw)) if raw else (None, None)

    async def create_model(self, provider_id: str, payload: dict[str, Any], user_id: str | None) -> dict[str, Any]:
        """创建模型。"""
        model_id = str(uuid.uuid4())
        encrypted_key, key_mask = self.key_values(payload.get("api_key"))
        async with self._engine.begin() as conn:
            await conn.execute(text(
                """
                INSERT INTO models(
                  id, provider_id, model_name, display_name, model_type, usage_position,
                  encrypted_key, key_mask, context_window, status, remark, created_by, updated_by
                ) VALUES(:id,:provider_id,:model_name,:display_name,:model_type,:usage_position,
                  :encrypted_key,:key_mask,:context_window,:status,:remark,:created_by,:updated_by)
                """
            ), {
                **payload,
                "id": model_id,
                "provider_id": provider_id,
                "encrypted_key": encrypted_key,
                "key_mask": key_mask,
                "context_window": nullable_int(payload.get("context_window")),
                "created_by": user_id,
                "updated_by": user_id,
            })
        return await self.get_model_with_provider(model_id) or {}

    async def update_model(self, model_id: str, payload: dict[str, Any], user_id: str | None) -> dict[str, Any]:
        """更新模型基础信息，传入新 Key 时替换当前 Key。"""
        encrypted_key, key_mask = self.key_values(payload.get("api_key"))
        key_sql = ", encrypted_key=:encrypted_key, key_mask=:key_mask" if encrypted_key else ""
        context_sql = ", context_window=:context_window" if "context_window" in payload else ""
        params = {**payload, "id": model_id, "updated_by": user_id, "encrypted_key": encrypted_key, "key_mask": key_mask}
        params["context_window"] = nullable_int(payload.get("context_window"))
        async with self._engine.begin() as conn:
            result = await conn.execute(text(
                f"""
                UPDATE models
                SET model_name=:model_name, display_name=:display_name, model_type=:model_type,
                    usage_position=:usage_position{context_sql}, status=:status, remark=:remark,
                    updated_by=:updated_by{key_sql}
                WHERE id=:id
                """
            ), params)
            if not result.rowcount:
                raise ValueError("模型不存在。")
        return await self.get_model_with_provider(model_id) or {}

    async def update_model_key(self, model_id: str, api_key: str, user_id: str | None) -> dict[str, Any]:
        """设置或替换模型唯一当前 Key。"""
        encrypted_key, key_mask = self.key_values(api_key)
        async with self._engine.begin() as conn:
            result = await conn.execute(text(
                """
                UPDATE models SET encrypted_key=:encrypted_key, key_mask=:key_mask,
                    last_test_status='unknown', last_test_message=NULL, last_test_at=NULL, updated_by=:updated_by
                WHERE id=:id
                """
            ), {"id": model_id, "encrypted_key": encrypted_key, "key_mask": key_mask, "updated_by": user_id})
            if not result.rowcount:
                raise ValueError("模型不存在。")
        return await self.get_model_with_provider(model_id) or {}

    async def update_model_test_result(self, model_id: str, *, ok: bool, message: str) -> None:
        """回写模型最近连通性测试结果。"""
        async with self._engine.begin() as conn:
            await conn.execute(text(
                """
                UPDATE models
                SET last_test_status=:status, last_test_message=:message, last_test_at=UTC_TIMESTAMP(3)
                WHERE id=:id
                """
            ), {"id": model_id, "status": "success" if ok else "failed", "message": message[:512]})

    async def set_model_status(self, model_id: str, status: str, user_id: str | None) -> dict[str, Any]:
        """启用或禁用模型。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("UPDATE models SET status=:status, updated_by=:updated_by WHERE id=:id"),
                {"id": model_id, "status": status, "updated_by": user_id},
            )
            if not result.rowcount:
                raise ValueError("模型不存在。")
        return await self.get_model_with_provider(model_id) or {}

    async def delete_model(self, model_id: str) -> None:
        """删除模型。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(text("DELETE FROM models WHERE id=:id"), {"id": model_id})
            if not result.rowcount:
                raise ValueError("模型不存在。")
