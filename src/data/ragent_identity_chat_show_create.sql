-- users
CREATE TABLE `users` (
  `id` char(36) NOT NULL COMMENT '用户ID，UUID',
  `email` varchar(255) NOT NULL COMMENT '登录邮箱，唯一',
  `password_hash` varchar(255) NOT NULL COMMENT '密码哈希，禁止存明文密码',
  `name` varchar(80) NOT NULL COMMENT '用户显示名称',
  `status` enum('active','disabled','pending') NOT NULL DEFAULT 'active' COMMENT '用户状态：active=正常，disabled=禁用，pending=待启用',
  `is_admin` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否管理员：1=管理员，0=普通用户',
  `last_login_at` datetime(3) DEFAULT NULL COMMENT '最后登录时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_email` (`email`),
  KEY `idx_users_status` (`status`),
  KEY `idx_users_is_admin` (`is_admin`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='RAGENT身份域用户表：登录注册、账号状态、管理员标记';

-- auth_sessions
CREATE TABLE `auth_sessions` (
  `token_hash` char(64) NOT NULL COMMENT 'refresh token SHA256摘要',
  `user_id` char(36) NOT NULL COMMENT '用户ID，对应 users.id',
  `ip_address` varchar(64) DEFAULT NULL COMMENT '登录IP',
  `user_agent` varchar(512) DEFAULT NULL COMMENT '登录User-Agent',
  `expires_at` datetime(3) NOT NULL COMMENT '过期时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  PRIMARY KEY (`token_hash`),
  KEY `idx_auth_sessions_user_id` (`user_id`),
  KEY `idx_auth_sessions_expires_at` (`expires_at`),
  CONSTRAINT `fk_auth_sessions_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='RAGENT身份域会话表：refresh token摘要和过期时间';

-- chat_conversations
CREATE TABLE `chat_conversations` (
  `id` char(36) NOT NULL COMMENT '聊天会话ID，UUID',
  `user_id` char(36) NOT NULL COMMENT '用户ID，对应 users.id',
  `title` varchar(255) NOT NULL COMMENT '聊天标题',
  `status` enum('active','archived','deleted') NOT NULL DEFAULT 'active' COMMENT '聊天状态：active=正常，archived=归档，deleted=删除',
  `last_message_at` datetime(3) DEFAULT NULL COMMENT '最后消息时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_chat_conversations_user_status_updated` (`user_id`,`status`,`updated_at`),
  KEY `idx_chat_conversations_last_message_at` (`last_message_at`),
  CONSTRAINT `fk_chat_conversations_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='RAGENT聊天域会话表：用户历史聊天列表';

-- chat_messages
CREATE TABLE `chat_messages` (
  `id` char(36) NOT NULL COMMENT '聊天消息ID，UUID',
  `conversation_id` char(36) NOT NULL COMMENT '聊天会话ID，对应 chat_conversations.id',
  `user_id` char(36) NOT NULL COMMENT '用户ID，对应 users.id',
  `role` enum('user','assistant','system') NOT NULL COMMENT '消息角色',
  `content` mediumtext NOT NULL COMMENT '消息正文',
  `metadata_json` json NOT NULL COMMENT 'SQL、结果行、图表、步骤、token、错误等结构化元数据',
  `trace_id` varchar(128) DEFAULT NULL COMMENT '关联 trace ID',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_chat_messages_conversation_created` (`conversation_id`,`created_at`),
  KEY `idx_chat_messages_user_created` (`user_id`,`created_at`),
  KEY `idx_chat_messages_trace_id` (`trace_id`),
  CONSTRAINT `fk_chat_messages_conversation_id` FOREIGN KEY (`conversation_id`) REFERENCES `chat_conversations` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_chat_messages_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `chk_chat_messages_metadata_json` CHECK ((json_type(`metadata_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='RAGENT聊天域消息表：用户消息、助手回答和问数结果元数据';
