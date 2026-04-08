# 数据库迁移

本目录包含 AI Agent 项目的数据库迁移脚本。

## 文件说明

- `001_init_generic_backend.sql` - AI Agent 通用后端基线迁移（create-only）
- `migrate.py` - 迁移执行脚本（使用 asyncpg）
- `verify_table.py` - `documents` 表结构验证脚本

## 迁移策略：create-only 基线

本项目采用 **create-only** 迁移策略：
- 仅展示 `CREATE TABLE` 语句，不包含 `DROP TABLE` 语句
- 适用于新库或清空库直接应用基线
- 历史迁移记录通过 `schema_migrations` 表管理
- 如需重建库，请先删除旧库后重新应用迁移

## 使用方法

### 执行迁移

```bash
uv run python migrations/migrate.py
```

### 验证表结构

```bash
uv run python migrations/verify_table.py
```

## 环境变量

迁移脚本使用以下环境变量（可通过 .env 文件配置）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DB_HOST | localhost | 数据库主机 |
| DB_PORT | 5432 | 数据库端口 |
| DB_USER | ai_workflow | 数据库用户 |
| DB_PASSWORD | ai_workflow | 数据库密码 |
| DB_NAME | ai_workflow | 数据库名称 |

## 表结构

### documents（通用文档表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | integer | PRIMARY KEY | 自增主键 |
| title | varchar(500) | NOT NULL | 文档标题 |
| content | text | NOT NULL | 文档完整内容 |
| summary | text | | 文档摘要，用于向量检索 |
| source_type | varchar(50) | DEFAULT 'markdown' | 来源类型 |
| embedding | vector(1024) | | 摘要的向量表示 |
| content_hash | varchar(64) | UNIQUE | 内容哈希（SHA256） |
| metadata | jsonb | DEFAULT '{}' | 扩展元数据 |
| created_at | timestamp | DEFAULT NOW() | 创建时间 |
| updated_at | timestamp | DEFAULT NOW() | 更新时间 |

### skills（技能定义表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | integer | PRIMARY KEY | 自增主键 |
| name | varchar(100) | UNIQUE NOT NULL | 技能唯一标识 |
| description | text | | 技能描述 |
| verification_token | varchar(100) | | 验证暗号 |
| metadata | jsonb | NOT NULL | 技能元数据 |
| content | text | NOT NULL | SKILL.md 内容 |
| tools | text | | TOOLS.md 内容 |
| is_static | boolean | DEFAULT true | 是否为静态技能 |
| created_at | timestamp | DEFAULT NOW() | 创建时间 |
| updated_at | timestamp | DEFAULT NOW() | 更新时间 |

### skill_references（技能参考资料表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | integer | PRIMARY KEY | 自增主键 |
| skill_id | integer | REFERENCES skills(id) | 关联技能 ID |
| file_path | varchar(500) | NOT NULL | 文件路径 |
| content | text | NOT NULL | 文件内容 |
| created_at | timestamp | DEFAULT NOW() | 创建时间 |

### conversations（对话记录表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | integer | PRIMARY KEY | 自增主键 |
| user_id | varchar(64) | NOT NULL | 用户 ID |
| conversation_id | varchar(64) | NOT NULL | 会话 ID |
| title | varchar(256) | DEFAULT '新会话' | 会话标题 |
| messages | jsonb | DEFAULT '[]' | 会话消息数组 |
| created_at | timestamp | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | timestamp | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

### conversation_sessions（会话元信息表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | integer | PRIMARY KEY | 自增主键 |
| user_id | varchar(64) | NOT NULL | 用户 ID |
| conversation_id | varchar(64) | NOT NULL | 会话 ID |
| title | varchar(256) | DEFAULT '新会话' | 会话标题 |
| created_at | timestamp | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | timestamp | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

### user_profiles（用户画像表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | integer | PRIMARY KEY | 自增主键 |
| user_id | varchar(64) | UNIQUE NOT NULL | 用户 ID |
| portrait_text | text | | 用户特征描述 |
| knowledge_text | text | | 用户知识背景 |
| preferences | jsonb | DEFAULT '{}' | 用户偏好设置 |
| created_at | timestamp | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | timestamp | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

## 索引

### documents
- `idx_documents_embedding` - 向量相似度索引（HNSW, cosine distance）
- `idx_documents_content_hash` - content_hash 索引
- `idx_documents_title_trgm` - 标题模糊搜索索引（gin + pg_trgm）

### skills
- `UNIQUE(name)` 约束索引（PostgreSQL 自动创建）- 技能名称唯一约束

### skill_references
- `UNIQUE(skill_id, file_path)` 约束索引（PostgreSQL 自动创建）- 防止同一技能重复引用同一路径

### conversations
- `idx_conversations_user_conv` - 用户+会话唯一索引
- `idx_conversations_created_at` - 创建时间索引

### conversation_sessions
- `idx_sessions_user_conv` - 用户+会话唯一索引
- `idx_sessions_user_id` - 用户 ID 索引

### user_profiles
- `idx_user_profiles_user_id` - 用户 ID 索引
