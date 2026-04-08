# 数据库表统一设计

## 背景

项目有三个模块涉及数据库操作：backend（旧后端）、backend-go（新后端）、ai_end_refactor（新AI端）。需要统一三者的表定义，以 backend（生产环境）为基准。

## 现状差异

| 差异项 | backend | backend-go | ai_end_refactor |
|--------|---------|------------|-----------------|
| user_id 类型 | UUID | uuid.UUID (Session) | VARCHAR(64) |
| 向量维度 | vector(1024) | **vector(1536)** | vector(1024) |
| AI端表定义 | - | 缺失 5 张表 | 完整 |

## 修改计划

### 1. ai_end_refactor — user_id 统一为 UUID

#### 1.1 SQL 迁移 (`migrations/001_init_generic_backend.sql`)

| 表名 | 旧类型 | 新类型 |
|------|--------|--------|
| conversations.user_id | VARCHAR(64) | UUID |
| conversation_sessions.user_id | VARCHAR(64) | UUID |
| user_profiles.user_id | VARCHAR(64) UNIQUE | UUID UNIQUE |

#### 1.2 Python 模型 (`src/api/models.py`, `src/api/compat_models.py`)

ChatRequest、ConversationCreate、AskCompatRequest、ClearMemoryCompatRequest 中的 `user_id` 字段添加 UUID 格式校验。

#### 1.3 迁移验证 (`migrations/migrate.py`)

schema 漂移检测中 user_id 列类型校验从 VARCHAR(64) 改为 UUID。

### 2. backend-go — 向量维度修复

`internal/model/vector.go`: `type:vector(1536)` → `type:vector(1024)`

### 3. backend-go — 新增 5 张 GORM 模型

每个表一个独立文件，与现有 user.go/session.go/article.go 风格一致。

#### 3.1 Conversation (`internal/model/conversation.go`)

- ID: uint64, primaryKey
- UserID: uuid.UUID, type:uuid, not null, index
- ConversationID: string, type:varchar(64), not null
- Title: string, type:varchar(256), default:'新会话'
- Messages: JSONArray, type:jsonb, default:'[]'
- CreatedAt, UpdatedAt: time.Time

#### 3.2 ConversationSession (`internal/model/conversation_session.go`)

- ID: uint64, primaryKey
- UserID: uuid.UUID, type:uuid, not null, index
- ConversationID: string, type:varchar(64), not null
- Title: string, type:varchar(256), default:'新会话'
- CreatedAt, UpdatedAt: time.Time

#### 3.3 UserProfile (`internal/model/user_profile.go`)

- ID: uint64, primaryKey
- UserID: uuid.UUID, type:uuid, uniqueIndex, not null
- PortraitText: *string, type:text
- KnowledgeText: *string, type:text
- Preferences: JSONMap, type:jsonb, default:'{}'
- CreatedAt, UpdatedAt: time.Time

#### 3.4 Skill (`internal/model/skill.go`)

- ID: uint32, primaryKey
- Name: string, type:varchar(100), uniqueIndex, not null
- Description: *string, type:text
- VerificationToken: *string, type:varchar(100)
- Metadata: JSONMap, type:jsonb, not null, default:'{}'
- Content: string, type:text, not null
- Tools: *string, type:text
- IsStatic: bool, default:true
- CreatedAt, UpdatedAt: time.Time

#### 3.5 SkillReference (`internal/model/skill_reference.go`)

- ID: uint32, primaryKey
- SkillID: uint32, index, not null
- FilePath: string, type:varchar(500), not null
- Content: string, type:text, not null
- CreatedAt: time.Time
- 复合唯一索引: (skill_id, file_path)

### 4. backend-go — AutoMigrate 更新

`internal/repository/db.go`: AutoMigrate 加入 Vector + 5 个新模型。

### 5. 新增 JSONMap 类型

复用现有 JSONArray 模式，新增 JSONMap 类型（map[string]interface{}）用于 jsonb 默认值 '{}' 的字段。

## 涉及文件清单

### ai_end_refactor (4 文件)
- `migrations/001_init_generic_backend.sql`
- `migrations/migrate.py`
- `src/api/models.py`
- `src/api/compat_models.py`

### backend-go (8 文件)
- `internal/model/vector.go` (修改向量维度)
- `internal/model/conversation.go` (新建)
- `internal/model/conversation_session.go` (新建)
- `internal/model/user_profile.go` (新建)
- `internal/model/skill.go` (新建)
- `internal/model/skill_reference.go` (新建)
- `internal/model/json_types.go` (新增 JSONMap)
- `internal/repository/db.go` (更新 AutoMigrate)
