# 数据库 Schema 同步修复设计（第二轮）

## 背景

2026-04-03 的初次 schema 同步已完成基础对齐（UUID 类型、向量维度、新增 5 个 GORM 模型）。但经系统性排查发现，Backend GORM AutoMigrate 与 ai_end SQL 迁移之间仍有 7 处残余差异。

## 约束与决策

- **单一真相源**：ai_end SQL 迁移 (`001_init_generic_backend.sql`)
- **数据库状态**：开发/测试环境，可重建，无需向后兼容 ALTER
- **GORM 策略**：保留 AutoMigrate，修正 gorm tag 使其与 ai_end SQL 一致
- **迁移系统**：双系统暂存，后续再淘汰 ai_end Python 迁移

## 方案

修正 GORM tag + 后端增量迁移 + crawler 补齐索引 + 文档修正。

---

## 修改清单

### 1. Go 模型 gorm tag 修正

#### 1.1 Article (`backend/internal/model/article.go`)

| 字段 | 当前 tag | 修正为 | 原因 |
|------|---------|--------|------|
| `PublishedOn` | `gorm:"index;not null"` | `gorm:"type:date;index;not null"` | ai_end SQL: `DATE NOT NULL` |

#### 1.2 Vector (`backend/internal/model/vector.go`)

| 字段 | 当前 tag | 修正为 | 原因 |
|------|---------|--------|------|
| `PublishedOn` | _(无)_ | `gorm:"type:date;not null"` | ai_end SQL: `DATE NOT NULL` |

#### 1.3 Conversation (`backend/internal/model/conversation.go`)

| 字段 | 当前 tag | 修正为 | 原因 |
|------|---------|--------|------|
| `ID` | `uint64` + `gorm:"primaryKey"` | `uint32` + `gorm:"primaryKey"` | ai_end SQL: `SERIAL`(int4) |

#### 1.4 ConversationSession (`backend/internal/model/conversation_session.go`)

| 字段 | 当前 tag | 修正为 | 原因 |
|------|---------|--------|------|
| `ID` | `uint64` + `gorm:"primaryKey"` | `uint32` + `gorm:"primaryKey"` | ai_end SQL: `SERIAL`(int4) |

#### 1.5 UserProfile (`backend/internal/model/user_profile.go`)

| 字段 | 当前 tag | 修正为 | 原因 |
|------|---------|--------|------|
| `ID` | `uint64` + `gorm:"primaryKey"` | `uint32` + `gorm:"primaryKey"` | ai_end SQL: `SERIAL`(int4) |

### 2. 新增后端迁移版本

在 `backend/internal/migration/versions.go` 新增 `2026041001_shared_table_fk_constraints`：

```sql
-- 添加 vectors → articles 外键（GORM tag 无法表达 FK）
ALTER TABLE vectors
  ADD CONSTRAINT fk_vectors_article
  FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE;

-- 添加 skill_references → skills 外键
ALTER TABLE skill_references
  ADD CONSTRAINT fk_skill_references_skill
  FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE;

-- 去除 vectors.article_id 冗余普通索引（2026040702 已创建 UNIQUE 索引）
DROP INDEX IF EXISTS idx_vectors_article_id;
```

同时新增对应测试。

### 3. 文档修正

#### 3.1 ai_end README (`ai_end/migrations/README.md`)

- 移除不存在的 `documents` 表描述，替换为 `articles` 表实际结构
- 移除 `idx_documents_*` 索引描述，替换为 `idx_articles_*` 实际索引
- 更新 `conversations.user_id` 类型描述从 VARCHAR(64) 改为 UUID

#### 3.2 root CLAUDE.md (`CLAUDE.md`)

- 移除不存在的 `messages` 表条目（消息存储在 `conversations.messages` JSONB 中）

## 涉及文件清单

| 文件 | 操作 |
|------|------|
| `backend/internal/model/article.go` | 修改 PublishedOn tag |
| `backend/internal/model/vector.go` | 修改 PublishedOn tag |
| `backend/internal/model/conversation.go` | ID uint64→uint32 |
| `backend/internal/model/conversation_session.go` | ID uint64→uint32 |
| `backend/internal/model/user_profile.go` | ID uint64→uint32 |
| `backend/internal/migration/versions.go` | 新增迁移版本 |
| `backend/internal/migration/migration_test.go` | 新增测试 |
| `crawler/db.py` | 补齐索引 |
| `ai_end/migrations/README.md` | 文档修正 |
| `CLAUDE.md` | 文档修正 |

## 不在范围内

- 迁移系统统一（后续再淘汰 ai_end Python 迁移）
- `created_at`/`updated_at` 的 TIMESTAMPTZ vs TIMESTAMP 差异（GORM 不支持在 tag 中指定 timewithtimezone，需自定义类型，投入产出比低）
