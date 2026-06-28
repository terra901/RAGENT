"""身份与聊天表 DDL。"""
from __future__ import annotations

IDENTITY_CHAT_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
      id CHAR(36) NOT NULL COMMENT '用户ID，UUID',
      email VARCHAR(255) NOT NULL COMMENT '登录邮箱，唯一',
      password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希，禁止存明文密码',
      name VARCHAR(80) NOT NULL COMMENT '用户显示名称',
      status ENUM('active','disabled','pending') NOT NULL DEFAULT 'active' COMMENT '用户状态',
      is_admin TINYINT(1) NOT NULL DEFAULT '0' COMMENT '是否管理员',
      last_login_at DATETIME(3) DEFAULT NULL COMMENT '最后登录时间',
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id), UNIQUE KEY uk_users_email (email),
      KEY idx_users_status (status), KEY idx_users_is_admin (is_admin)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT身份域用户表'
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
      token_hash CHAR(64) NOT NULL COMMENT 'refresh token SHA256摘要',
      user_id CHAR(36) NOT NULL COMMENT '用户ID',
      ip_address VARCHAR(64) DEFAULT NULL COMMENT '登录IP',
      user_agent VARCHAR(512) DEFAULT NULL COMMENT '登录User-Agent',
      expires_at DATETIME(3) NOT NULL COMMENT '过期时间',
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      PRIMARY KEY (token_hash), KEY idx_auth_sessions_user_id (user_id),
      KEY idx_auth_sessions_expires_at (expires_at),
      CONSTRAINT fk_auth_sessions_user_id FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT身份域会话表'
    """,
    """
    CREATE TABLE IF NOT EXISTS user_permissions (
      id CHAR(36) NOT NULL COMMENT '权限记录ID，UUID',
      user_id CHAR(36) NOT NULL COMMENT '用户ID',
      can_create_template TINYINT(1) NOT NULL DEFAULT '1',
      can_update_own_template TINYINT(1) NOT NULL DEFAULT '1',
      can_delete_own_template TINYINT(1) NOT NULL DEFAULT '1',
      can_view_public_template TINYINT(1) NOT NULL DEFAULT '1',
      can_publish_template TINYINT(1) NOT NULL DEFAULT '0',
      can_import_template TINYINT(1) NOT NULL DEFAULT '1',
      can_export_template TINYINT(1) NOT NULL DEFAULT '1',
      can_manage_users TINYINT(1) NOT NULL DEFAULT '0',
      can_manage_permissions TINYINT(1) NOT NULL DEFAULT '0',
      allowed_modules_json JSON NOT NULL COMMENT '允许使用的模块数组',
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id), UNIQUE KEY uk_user_permissions_user_id (user_id),
      CONSTRAINT fk_user_permissions_user_id FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
      CONSTRAINT chk_user_permissions_allowed_modules_json CHECK (JSON_TYPE(allowed_modules_json) = 'ARRAY')
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT用户权限表'
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_conversations (
      id CHAR(36) NOT NULL COMMENT '聊天会话ID，UUID',
      user_id CHAR(36) NOT NULL COMMENT '用户ID',
      title VARCHAR(255) NOT NULL COMMENT '聊天标题',
      status ENUM('active','archived','deleted') NOT NULL DEFAULT 'active',
      last_message_at DATETIME(3) DEFAULT NULL COMMENT '最后消息时间',
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id), KEY idx_chat_conversations_user_status_updated (user_id, status, updated_at),
      KEY idx_chat_conversations_last_message_at (last_message_at),
      CONSTRAINT fk_chat_conversations_user_id FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT聊天域会话表'
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
      id CHAR(36) NOT NULL COMMENT '聊天消息ID，UUID',
      conversation_id CHAR(36) NOT NULL COMMENT '聊天会话ID',
      user_id CHAR(36) NOT NULL COMMENT '用户ID',
      role ENUM('user','assistant','system') NOT NULL COMMENT '消息角色',
      content MEDIUMTEXT NOT NULL COMMENT '消息正文',
      metadata_json JSON NOT NULL COMMENT '结构化元数据',
      trace_id VARCHAR(128) DEFAULT NULL COMMENT '关联 trace ID',
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id), KEY idx_chat_messages_conversation_created (conversation_id, created_at),
      KEY idx_chat_messages_user_created (user_id, created_at), KEY idx_chat_messages_trace_id (trace_id),
      CONSTRAINT fk_chat_messages_conversation_id FOREIGN KEY (conversation_id) REFERENCES chat_conversations (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
      CONSTRAINT fk_chat_messages_user_id FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
      CONSTRAINT chk_chat_messages_metadata_json CHECK (JSON_TYPE(metadata_json) = 'OBJECT')
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='RAGENT聊天域消息表'
    """,
]
