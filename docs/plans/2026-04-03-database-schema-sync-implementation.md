# Database Schema Sync (Backend Baseline) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 以 `backend` 为数据库基线，统一 `ai_end_refactor` 与 `backend-go` 的表结构和类型约束，消除跨服务 schema 漂移。

**Architecture:** 采用“先测试失败、再最小实现、再验证通过”的 TDD 流程，分别在 Python 和 Go 两个子项目中落地。`ai_end_refactor` 负责请求模型与迁移 SQL 的 UUID 统一；`backend-go` 负责向量维度修正、缺失模型补齐、AutoMigrate 清单对齐。实现时优先复用已有模式（如 `JSONArray` 的 `Scanner/Valuer`）。

**Tech Stack:** Python 3.11, Pydantic v2, pytest/pytest-asyncio, asyncpg, Go 1.21, GORM, PostgreSQL(pgvector/jsonb)

---

## 执行约束

- 必须遵循 `@superpowers:test-driven-development`：每个任务先写失败测试，再写最小实现。
- 完成前必须执行 `@superpowers:verification-before-completion` 的验证步骤。
- **约束：不自动提交代码。** 本计划中的第 5 步统一为“检查点（不提交）”，只运行状态检查，不执行 `git commit`。

### Task 1: AI API 请求模型 UUID 校验（models + compat_models）

**Files:**
- Modify: `ai_end_refactor/src/api/models.py:1-25`
- Modify: `ai_end_refactor/src/api/compat_models.py:1-30`
- Modify: `ai_end_refactor/tests/unit/test_api_models.py:1-30`
- Modify: `ai_end_refactor/tests/unit/test_api_main.py:63-170`
- Modify: `ai_end_refactor/tests/integration/test_compat_endpoints.py:120-220`
- Test: `ai_end_refactor/tests/unit/test_api_models.py`

**Step 1: Write the failing test**

在 `ai_end_refactor/tests/unit/test_api_models.py` 增加 UUID 合法/非法用例（先失败）：

```python
import pytest
from pydantic import ValidationError

from src.api.models import ChatRequest, ConversationCreate
from src.api.compat_models import AskCompatRequest, ClearMemoryCompatRequest

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"


def test_chat_request_rejects_invalid_user_id_uuid():
    with pytest.raises(ValidationError, match="user_id must be a valid UUID"):
        ChatRequest(message="hi", user_id="u1")


def test_conversation_create_accepts_uuid_user_id():
    req = ConversationCreate(user_id=VALID_UUID, title="考研咨询")
    assert req.user_id == VALID_UUID


def test_compat_models_validate_uuid_user_id():
    req = AskCompatRequest(question="test", user_id=VALID_UUID)
    assert req.user_id == VALID_UUID

    with pytest.raises(ValidationError, match="user_id must be a valid UUID"):
        ClearMemoryCompatRequest(user_id="bad-user")
```

并将现有使用 `"u1"` / `"user123"` / `"test_user"` 的请求模型构造，统一替换为合法 UUID 字符串常量。

**Step 2: Run test to verify it fails**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_api_models.py -v
```

Expected: FAIL，提示当前模型仅做长度限制或未做 UUID 格式校验。

**Step 3: Write minimal implementation**

在 `ai_end_refactor/src/api/models.py` 与 `ai_end_refactor/src/api/compat_models.py` 增加最小 UUID 校验（保持字段类型为 `str`，避免下游服务类型连锁改动）：

```python
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str
    user_id: str = Field(min_length=1, max_length=64)
    conversation_id: str | None = None

    @field_validator("user_id")
    @classmethod
    def _validate_user_id_uuid(cls, v: str) -> str:
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc
```

```python
class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None

    @field_validator("user_id")
    @classmethod
    def _validate_optional_user_id_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc
```

**Step 4: Run test to verify it passes**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_api_models.py tests/unit/test_api_main.py tests/integration/test_compat_endpoints.py -v
```

Expected: PASS（若仍失败，按报错把请求体中的 `user_id` 测试数据继续替换为合法 UUID）。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: 仅出现本任务计划内文件变更；**不执行 `git commit`**。

---

### Task 2: AI 基线迁移 SQL 中 user_id 改为 UUID

**Files:**
- Modify: `ai_end_refactor/migrations/001_init_generic_backend.sql:69-106`
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:220-340`
- Test: `ai_end_refactor/tests/unit/test_migrate.py`

**Step 1: Write the failing test**

在 `ai_end_refactor/tests/unit/test_migrate.py` 添加契约测试：

```python
def test_baseline_migration_uses_uuid_for_chat_tables_user_id():
    migrations_dir = Path(migrate.__file__).parent
    baseline = migrations_dir / "001_init_generic_backend.sql"
    content = baseline.read_text(encoding="utf-8").lower().replace("\n", " ")

    assert "conversations" in content
    assert "conversation_sessions" in content
    assert "user_profiles" in content
    assert "user_id uuid" in content
    assert "user_id varchar(64)" not in content
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_migrate.py::test_baseline_migration_uses_uuid_for_chat_tables_user_id -v
```

Expected: FAIL，当前 SQL 仍包含 `user_id VARCHAR(64)`。

**Step 3: Write minimal implementation**

修改 `ai_end_refactor/migrations/001_init_generic_backend.sql`：

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    ...
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    ...
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL,
    ...
);
```

**Step 4: Run test to verify it passes**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_migrate.py::test_baseline_migration_uses_uuid_for_chat_tables_user_id -v
```

Expected: PASS。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: SQL 与测试文件变更可见；**不执行 `git commit`**。

---

### Task 3: migrate.py 的 schema 漂移检测与 auto-repair 对齐 UUID

**Files:**
- Modify: `ai_end_refactor/migrations/migrate.py:45-210`
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:140-320`
- Test: `ai_end_refactor/tests/unit/test_migrate.py`

**Step 1: Write the failing test**

在 `test_migrate.py` 添加“必须检测 user_id 类型为 uuid”的失败用例：

```python
@pytest.mark.asyncio
async def test_schema_drift_detects_non_uuid_user_id_columns(monkeypatch):
    class TypeFakeConn(FakeConn):
        async def fetchval(self, query: str, *args):
            q = " ".join(query.lower().split())
            if "from information_schema.columns" in q and "data_type" in q:
                table_name, column_name = args
                if (table_name, column_name) in {
                    ("conversations", "user_id"),
                    ("conversation_sessions", "user_id"),
                    ("user_profiles", "user_id"),
                }:
                    return "character varying"
                return "uuid"
            return True

    drift = await migrate._has_schema_drift(TypeFakeConn())
    assert drift is True
```

并新增 auto-repair SQL 断言：

```python
@pytest.mark.asyncio
async def test_apply_schema_repair_uses_uuid_user_id_for_chat_tables():
    fake_conn = FakeConn()
    await migrate._apply_schema_repair(fake_conn)
    executed_sql = "\n".join(fake_conn.executed_sql).lower()
    assert "create table if not exists conversations" in executed_sql
    assert "user_id uuid not null" in executed_sql
    assert "user_id varchar(64)" not in executed_sql
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_migrate.py::test_schema_drift_detects_non_uuid_user_id_columns tests/unit/test_migrate.py::test_apply_schema_repair_uses_uuid_user_id_for_chat_tables -v
```

Expected: FAIL，当前 `_has_schema_drift` 未校验类型，repair SQL 仍是 `VARCHAR(64)`。

**Step 3: Write minimal implementation**

在 `ai_end_refactor/migrations/migrate.py` 增加 user_id 类型校验，并同步修复 SQL：

```python
uuid_type_checks = [
    ("conversations", "user_id", "uuid"),
    ("conversation_sessions", "user_id", "uuid"),
    ("user_profiles", "user_id", "uuid"),
]

for table_name, column_name, expected_type in uuid_type_checks:
    data_type = await conn.fetchval(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
          AND column_name = $2
        """,
        table_name,
        column_name,
    )
    if data_type != expected_type:
        return True
```

并将 `_apply_schema_repair` 中三张表 `user_id` 定义改成 `UUID`。

**Step 4: Run test to verify it passes**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_migrate.py -v
```

Expected: PASS（含新增 UUID 漂移检测用例）。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: `migrate.py` 与对应测试文件已变更；**不执行 `git commit`**。

---

### Task 4: backend-go 向量维度修复 + JSONMap 类型补齐

**Files:**
- Modify: `backend-go/internal/model/vector.go:7-13`
- Create: `backend-go/internal/model/json_types.go`
- Create: `backend-go/internal/model/json_types_test.go`
- Create: `backend-go/internal/model/vector_test.go`
- Test: `backend-go/internal/model/*.go`

**Step 1: Write the failing test**

新增 `vector_test.go` 与 `json_types_test.go`：

```go
package model

import (
    "reflect"
    "strings"
    "testing"
)

func TestVectorEmbeddingTagUses1024Dimension(t *testing.T) {
    field, ok := reflect.TypeOf(Vector{}).FieldByName("Embedding")
    if !ok {
        t.Fatal("Embedding field not found")
    }
    tag := field.Tag.Get("gorm")
    if !strings.Contains(tag, "vector(1024)") {
        t.Fatalf("expected vector(1024), got %s", tag)
    }
}
```

```go
package model

import (
    "encoding/json"
    "testing"
)

func TestJSONMap_Value_NilReturnsEmptyObject(t *testing.T) {
    var m JSONMap
    val, err := m.Value()
    if err != nil {
        t.Fatalf("Value failed: %v", err)
    }
    if val != "{}" {
        t.Fatalf("expected {}, got %v", val)
    }
}

func TestJSONMap_Scan_ByteSlice(t *testing.T) {
    var m JSONMap
    if err := m.Scan([]byte(`{"k":"v"}`)); err != nil {
        t.Fatalf("Scan failed: %v", err)
    }
    if m["k"] != "v" {
        t.Fatalf("expected v, got %v", m["k"])
    }

    raw, _ := m.Value()
    var decoded map[string]any
    _ = json.Unmarshal(raw.([]byte), &decoded)
    if decoded["k"] != "v" {
        t.Fatalf("expected v after marshal, got %v", decoded["k"])
    }
}
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend-go
go test ./internal/model -run "TestVectorEmbeddingTagUses1024Dimension|TestJSONMap_" -v
```

Expected: FAIL（`vector(1536)` 不匹配，且 `JSONMap` 尚未定义）。

**Step 3: Write minimal implementation**

在 `vector.go` 修改维度：

```go
Embedding []float32 `gorm:"type:vector(1024)"`
```

新增 `json_types.go`，复用 `JSONArray` 模式：

```go
package model

import (
    "database/sql/driver"
    "encoding/json"
    "fmt"
)

type JSONMap map[string]any

func (m *JSONMap) Scan(value interface{}) error {
    if value == nil {
        *m = nil
        return nil
    }

    var data []byte
    switch v := value.(type) {
    case []byte:
        data = v
    case string:
        data = []byte(v)
    default:
        return fmt.Errorf("cannot scan %T into JSONMap", value)
    }

    if len(data) == 0 {
        *m = nil
        return nil
    }

    return json.Unmarshal(data, m)
}

func (m JSONMap) Value() (driver.Value, error) {
    if m == nil {
        return "{}", nil
    }
    return json.Marshal(m)
}
```

**Step 4: Run test to verify it passes**

Run:

```bash
cd backend-go
go test ./internal/model -run "TestVectorEmbeddingTagUses1024Dimension|TestJSONMap_" -v
```

Expected: PASS。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: model 层目标文件有变更；**不执行 `git commit`**。

---

### Task 5: backend-go 新增 5 张缺失模型（Conversation/Session/Profile/Skill/SkillReference）

**Files:**
- Create: `backend-go/internal/model/conversation.go`
- Create: `backend-go/internal/model/conversation_session.go`
- Create: `backend-go/internal/model/user_profile.go`
- Create: `backend-go/internal/model/skill.go`
- Create: `backend-go/internal/model/skill_reference.go`
- Create: `backend-go/internal/model/schema_models_test.go`
- Test: `backend-go/internal/model/schema_models_test.go`

**Step 1: Write the failing test**

新增 `schema_models_test.go`，用反射校验核心 gorm tag：

```go
package model

import (
    "reflect"
    "strings"
    "testing"
)

func TestUserProfileUserIDUsesUUIDUniqueIndex(t *testing.T) {
    field, _ := reflect.TypeOf(UserProfile{}).FieldByName("UserID")
    tag := field.Tag.Get("gorm")
    if !strings.Contains(tag, "type:uuid") || !strings.Contains(tag, "uniqueIndex") {
        t.Fatalf("unexpected UserProfile.UserID tag: %s", tag)
    }
}

func TestSkillReferenceHasCompositeUniqueIndexTag(t *testing.T) {
    typ := reflect.TypeOf(SkillReference{})
    skillID, _ := typ.FieldByName("SkillID")
    filePath, _ := typ.FieldByName("FilePath")

    if !strings.Contains(skillID.Tag.Get("gorm"), "uniqueIndex:idx_skill_file") {
        t.Fatalf("SkillID missing composite unique index tag")
    }
    if !strings.Contains(filePath.Tag.Get("gorm"), "uniqueIndex:idx_skill_file") {
        t.Fatalf("FilePath missing composite unique index tag")
    }
}
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend-go
go test ./internal/model -run "TestUserProfileUserIDUsesUUIDUniqueIndex|TestSkillReferenceHasCompositeUniqueIndexTag" -v
```

Expected: FAIL（结构体尚未定义）。

**Step 3: Write minimal implementation**

按设计新建 5 个模型文件（每表一个文件）：

```go
// conversation.go
package model

import (
    "time"

    "github.com/google/uuid"
)

type Conversation struct {
    ID             uint64    `gorm:"primaryKey"`
    UserID         uuid.UUID `gorm:"type:uuid;not null;index"`
    ConversationID string    `gorm:"type:varchar(64);not null"`
    Title          string    `gorm:"type:varchar(256);default:'新会话'"`
    Messages       JSONArray `gorm:"type:jsonb;default:'[]'"`
    CreatedAt      time.Time
    UpdatedAt      time.Time
}
```

```go
// conversation_session.go
package model

import (
    "time"

    "github.com/google/uuid"
)

type ConversationSession struct {
    ID             uint64    `gorm:"primaryKey"`
    UserID         uuid.UUID `gorm:"type:uuid;not null;index"`
    ConversationID string    `gorm:"type:varchar(64);not null"`
    Title          string    `gorm:"type:varchar(256);default:'新会话'"`
    CreatedAt      time.Time
    UpdatedAt      time.Time
}
```

```go
// user_profile.go
package model

import (
    "time"

    "github.com/google/uuid"
)

type UserProfile struct {
    ID            uint64    `gorm:"primaryKey"`
    UserID        uuid.UUID `gorm:"type:uuid;not null;uniqueIndex"`
    PortraitText  *string   `gorm:"type:text"`
    KnowledgeText *string   `gorm:"type:text"`
    Preferences   JSONMap   `gorm:"type:jsonb;default:'{}'"`
    CreatedAt     time.Time
    UpdatedAt     time.Time
}
```

```go
// skill.go
package model

import "time"

type Skill struct {
    ID                uint32  `gorm:"primaryKey"`
    Name              string  `gorm:"type:varchar(100);not null;uniqueIndex"`
    Description       *string `gorm:"type:text"`
    VerificationToken *string `gorm:"type:varchar(100)"`
    Metadata          JSONMap `gorm:"type:jsonb;not null;default:'{}'"`
    Content           string  `gorm:"type:text;not null"`
    Tools             *string `gorm:"type:text"`
    IsStatic          bool    `gorm:"default:true"`
    CreatedAt         time.Time
    UpdatedAt         time.Time
}
```

```go
// skill_reference.go
package model

import "time"

type SkillReference struct {
    ID        uint32    `gorm:"primaryKey"`
    SkillID   uint32    `gorm:"not null;index;uniqueIndex:idx_skill_file"`
    FilePath  string    `gorm:"type:varchar(500);not null;uniqueIndex:idx_skill_file"`
    Content   string    `gorm:"type:text;not null"`
    CreatedAt time.Time
}
```

**Step 4: Run test to verify it passes**

Run:

```bash
cd backend-go
go test ./internal/model -run "TestUserProfileUserIDUsesUUIDUniqueIndex|TestSkillReferenceHasCompositeUniqueIndexTag" -v
```

Expected: PASS。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: 新模型文件与测试文件变更可见；**不执行 `git commit`**。

---

### Task 6: backend-go AutoMigrate 纳入 Vector + 5 新模型

**Files:**
- Modify: `backend-go/internal/repository/db.go:1-35`
- Create: `backend-go/internal/repository/db_test.go`
- Test: `backend-go/internal/repository/db_test.go`

**Step 1: Write the failing test**

为 `db.go` 增加可测试的模型清单函数，并先在测试中约束目标集合（先写测试）：

```go
package repository

import (
    "reflect"
    "testing"
)

func TestAutoMigrateModelsIncludesSchemaSyncModels(t *testing.T) {
    models := autoMigrateModels()

    got := map[string]bool{}
    for _, m := range models {
        got[reflect.TypeOf(m).Elem().Name()] = true
    }

    expected := []string{
        "User", "Session", "Article", "Vector",
        "Conversation", "ConversationSession", "UserProfile",
        "Skill", "SkillReference",
    }

    for _, name := range expected {
        if !got[name] {
            t.Fatalf("missing model in AutoMigrate list: %s", name)
        }
    }
}
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend-go
go test ./internal/repository -run TestAutoMigrateModelsIncludesSchemaSyncModels -v
```

Expected: FAIL（`autoMigrateModels` 未定义，或模型列表不完整）。

**Step 3: Write minimal implementation**

在 `backend-go/internal/repository/db.go` 提取并使用模型清单：

```go
func autoMigrateModels() []interface{} {
    return []interface{}{
        &model.User{},
        &model.Session{},
        &model.Article{},
        &model.Vector{},
        &model.Conversation{},
        &model.ConversationSession{},
        &model.UserProfile{},
        &model.Skill{},
        &model.SkillReference{},
    }
}

func InitDB(databaseURL string) error {
    ...
    if err := DB.AutoMigrate(autoMigrateModels()...); err != nil {
        return err
    }
    ...
}
```

**Step 4: Run test to verify it passes**

Run:

```bash
cd backend-go
go test ./internal/repository -run TestAutoMigrateModelsIncludesSchemaSyncModels -v
```

Expected: PASS。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: `db.go` 与 `db_test.go` 变更可见；**不执行 `git commit`**。

---

### Task 7: 端到端回归验证（Python + Go）

**Files:**
- Test only: `ai_end_refactor/tests/unit/test_api_models.py`
- Test only: `ai_end_refactor/tests/unit/test_migrate.py`
- Test only: `backend-go/internal/model/*.go`
- Test only: `backend-go/internal/repository/*.go`

**Step 1: Write the failing test**

本任务为验证任务，无新增业务测试；使用前序任务已新增测试作为回归基线。

**Step 2: Run test to verify it fails (optional smoke before full run)**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_api_models.py tests/unit/test_migrate.py -v
```

若此步失败，先修复再进入全量验证。

**Step 3: Write minimal implementation**

无新增实现，仅修复第 2 步暴露的问题，保持 DRY/YAGNI。

**Step 4: Run test to verify it passes**

Run:

```bash
cd ai_end_refactor
uv run pytest tests/unit/test_api_models.py tests/unit/test_migrate.py -v
```

Run:

```bash
cd ../backend-go
go test ./internal/model ./internal/repository -v
```

Expected: PASS。

**Step 5: Checkpoint (no commit)**

Run:

```bash
git status --short
```

Expected: 所有变更均来自计划内文件；**不执行 `git commit`**。

---

## 风险与回滚点

- UUID 校验会让历史测试数据（`u1`、`user123`）失效：先集中替换测试数据，再看真实业务是否仍有非 UUID 调用方。
- `migrate.py` 类型检测增强后，历史库若未迁移会被判定漂移：需确保 auto-repair SQL 已同步 UUID。
- Go 端新增模型后 AutoMigrate 会创建新表：先在测试环境跑迁移验证，确认不影响现有业务表。

## 完成定义（DoD）

- `ai_end_refactor`：请求模型与迁移 SQL 中 `user_id` 均为 UUID 语义，相关测试通过。
- `backend-go`：`vector(1024)`、`JSONMap`、5 张新模型、AutoMigrate 清单全部到位，相关测试通过。
- 全流程未执行自动提交命令，满足“禁止自动提交代码”约束。
