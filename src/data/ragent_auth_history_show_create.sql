-- ragent_users
CREATE TABLE `ragent_users` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID，UUID',
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录邮箱，唯一',
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'PBKDF2-SHA256密码哈希',
  `name` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户显示名称',
  `status` enum('active','disabled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT '用户状态',
  `is_admin` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否管理员',
  `last_login_at` datetime(3) DEFAULT NULL COMMENT '最后登录时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ragent_users_email` (`email`),
  KEY `idx_ragent_users_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAGENT用户表：登录注册和账号状态';

-- ragent_auth_sessions
CREATE TABLE `ragent_auth_sessions` (
  `token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'refresh token SHA256摘要',
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID',
  `ip_address` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '登录IP',
  `user_agent` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '登录User-Agent',
  `expires_at` datetime(3) NOT NULL COMMENT '过期时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  PRIMARY KEY (`token_hash`),
  KEY `idx_ragent_auth_sessions_user_id` (`user_id`),
  KEY `idx_ragent_auth_sessions_expires_at` (`expires_at`),
  CONSTRAINT `fk_ragent_auth_sessions_user_id` FOREIGN KEY (`user_id`) REFERENCES `ragent_users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAGENT refresh token会话表';

-- ragent_conversations
CREATE TABLE `ragent_conversations` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '对话ID，UUID',
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '对话标题',
  `archived` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否归档',
  `last_message_at` datetime(3) DEFAULT NULL COMMENT '最后消息时间',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  `updated_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ragent_conversations_user_archived_updated` (`user_id`,`archived`,`updated_at`),
  KEY `idx_ragent_conversations_last_message_at` (`last_message_at`),
  CONSTRAINT `fk_ragent_conversations_user_id` FOREIGN KEY (`user_id`) REFERENCES `ragent_users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAGENT历史对话表';

-- ragent_conversation_messages
CREATE TABLE `ragent_conversation_messages` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息ID，UUID',
  `conversation_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '对话ID',
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID',
  `role` enum('user','assistant') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息角色',
  `content` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息正文',
  `metadata_json` json NOT NULL COMMENT 'SQL、结果行、图表、步骤、token等结构化元数据',
  `trace_id` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '关联trace ID',
  `created_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_ragent_messages_conversation_created` (`conversation_id`,`created_at`),
  KEY `idx_ragent_messages_user_created` (`user_id`,`created_at`),
  KEY `idx_ragent_messages_trace_id` (`trace_id`),
  CONSTRAINT `fk_ragent_messages_conversation_id` FOREIGN KEY (`conversation_id`) REFERENCES `ragent_conversations` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_ragent_messages_user_id` FOREIGN KEY (`user_id`) REFERENCES `ragent_users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `chk_ragent_messages_metadata_json` CHECK ((json_type(`metadata_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAGENT历史对话消息表';
