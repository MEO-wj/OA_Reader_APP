# 数据库 Schema 同步修复（第二轮）Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 backend GORM AutoMigrate 与 ai_end SQL 基线迁移的剩余差异全部对齐，消除第二轮 schema 漂移点并保持可回归验证。

**Architecture:** 以 ai_end 迁移 SQL 为单一真相源，采用“测试先行 -> 最小实现 -> 验证通过”的 TDD 流程逐项修复模型、迁移、爬虫索引与文档。优先复用现有测试文件与断言风格，避免引入新的测试框架和复杂基础设施。每个任务单独提交，降低回滚半径与后续技术债。

**Tech Stack:** Go 1.21, GORM, PostgreSQL, Python 3.11, psycopg3, pytest, ripgrep

---

## 执行前约束

- 工作流技能：@superpowers:writing-plans（本计划已完成）
- 执行技能：@superpowers:executing-plans
- 过程约束：@superpowers:test-driven-development
- 收尾约束：@superpowers:verification-before-completion
- 必须在独立 worktree 执行（若未创建，先用 @superpowers:using-git-worktrees）

---

### Task 1: 对齐 Article/Vector 的 DATE gorm tag

**Files:**
- Modify: `backend/internal/model/article.go`
- Modify: `backend/internal/model/vector.go`
- Modify: `backend/internal/model/schema_models_test.go`
- Modify: `backend/internal/model/vector_test.go`
- Test: `backend/internal/model/schema_models_test.go`

**Step 1: Write the failing test**

在 `backend/internal/model/schema_models_test.go` 新增反射断言：

```go
func TestArticlePublishedOnUsesDateTypeTag(t *testing.T) {
	field, ok := reflect.TypeOf(Article{}).FieldByName("PublishedOn")
	if !ok {
		t.Fatal("Article.PublishedOn not found")
	}
	tag := field.Tag.Get("gorm")
	if !strings.Contains(tag, "type:date") {
		t.Fatalf("expected type:date in tag, got %s", tag)
	}
}

func TestVectorPublishedOnUsesDateTypeAndNotNullTag(t *testing.T) {
	field, ok := reflect.TypeOf(Vector{}).FieldByName("PublishedOn")
	if !ok {
		t.Fatal("Vector.PublishedOn not found")
	}
	tag := field.Tag.Get("gorm")
	if !strings.Contains(tag, "type:date") || !strings.Contains(tag, "not null") {
		t.Fatalf("unexpected Vector.PublishedOn tag: %s", tag)
	}
}
```

在 `backend/internal/model/vector_test.go` 保持维度断言不变，只补充一条 PublishedOn tag 断言（与该文件现有风格一致）。

**Step 2: Run test to verify it fails**

Run: `cd backend && go test ./internal/model -run "TestArticlePublishedOnUsesDateTypeTag|TestVectorPublishedOnUsesDateTypeAndNotNullTag" -v`

Expected: FAIL，提示 tag 未包含 `type:date`。

**Step 3: Write minimal implementation**

在模型中最小改动：

```go
PublishedOn time.Time `gorm:"type:date;index;not null" json:"published_on"`
```

```go
PublishedOn time.Time `gorm:"type:date;not null"`
```

**Step 4: Run test to verify it passes**

Run: `cd backend && go test ./internal/model -run "TestArticlePublishedOnUsesDateTypeTag|TestVectorPublishedOnUsesDateTypeAndNotNullTag|TestVectorEmbeddingTagUses1024Dimension" -v`

Expected: PASS。

---

### Task 2: 对齐 3 个模型主键类型为 uint32（映射 SERIAL/int4）

**Files:**
- Modify: `backend/internal/model/conversation.go`
- Modify: `backend/internal/model/conversation_session.go`
- Modify: `backend/internal/model/user_profile.go`
- Modify: `backend/internal/model/schema_models_test.go`
- Test: `backend/internal/model/schema_models_test.go`

**Step 1: Write the failing test**

在 `backend/internal/model/schema_models_test.go` 新增主键类型断言：

```go
func TestConversationLikeModelsUseUint32PrimaryKey(t *testing.T) {
	cases := []struct {
		name string
		typ  reflect.Type
	}{
		{name: "Conversation", typ: reflect.TypeOf(Conversation{})},
		{name: "ConversationSession", typ: reflect.TypeOf(ConversationSession{})},
		{name: "UserProfile", typ: reflect.TypeOf(UserProfile{})},
	}

	for _, tc := range cases {
		field, ok := tc.typ.FieldByName("ID")
		if !ok {
			t.Fatalf("%s.ID not found", tc.name)
		}
		if field.Type.Kind() != reflect.Uint32 {
			t.Fatalf("%s.ID expected uint32, got %s", tc.name, field.Type.Kind())
		}
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && go test ./internal/model -run TestConversationLikeModelsUseUint32PrimaryKey -v`

Expected: FAIL，当前为 `uint64`。

**Step 3: Write minimal implementation**

分别修改：

```go
ID uint32 `gorm:"primaryKey"`
```

应用到 3 个模型。

**Step 4: Run test to verify it passes**

Run: `cd backend && go test ./internal/model -run "TestConversationLikeModelsUseUint32PrimaryKey|TestConversationAndSessionUseDistinctCompositeUniqueIndexTags|TestUserProfileUserIDUsesUUIDUniqueIndex" -v`

Expected: PASS。

---

### Task 3: 新增后端迁移版本（FK + 冗余索引清理）

**Files:**
- Modify: `backend/internal/migration/versions.go`
- Modify: `backend/internal/migration/migration_test.go`
- Test: `backend/internal/migration/migration_test.go`

**Step 1: Write the failing test**

在 `backend/internal/migration/migration_test.go` 按现有风格新增版本存在性测试：

```go
func TestDefaultVersions_ContainsSharedTableFkConstraintsMigration(t *testing.T) {
	versions := DefaultVersions(nil)
	ids := make([]string, 0, len(versions))
	for _, v := range versions {
		ids = append(ids, v.ID)
	}

	if !slices.Contains(ids, "2026041001_shared_table_fk_constraints") {
		t.Fatalf("missing migration 2026041001_shared_table_fk_constraints, got: %#v", ids)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && go test ./internal/migration -run TestDefaultVersions_ContainsSharedTableFkConstraintsMigration -v`

Expected: FAIL，尚未注册该版本。

**Step 3: Write minimal implementation**

在 `DefaultVersions` 末尾新增：

```go
{
	ID: "2026041001_shared_table_fk_constraints",
	Up: func(tx *gorm.DB) error {
		return tx.Exec(`
			ALTER TABLE vectors
			  ADD CONSTRAINT fk_vectors_article
			  FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE;

			ALTER TABLE skill_references
			  ADD CONSTRAINT fk_skill_references_skill
			  FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE;

			DROP INDEX IF EXISTS idx_vectors_article_id;
		`).Error
	},
},
```

如需幂等性，按项目当前迁移风格补 `DO $$ ... IF NOT EXISTS ... $$;` 防止重复应用报错。

**Step 4: Run test to verify it passes**

Run: `cd backend && go test ./internal/migration -run "TestDefaultVersions_ContainsSharedTableFkConstraintsMigration|TestRunnerRun_AppliesPendingVersionsOnce" -v`

Expected: PASS。


---

### Task 4: crawler 初始化补齐向量索引（与 ai_end 基线一致）

**Files:**
- Modify: `crawler/db.py`
- Modify: `crawler/tests/test_init_db_defaults.py`
- Test: `crawler/tests/test_init_db_defaults.py`

**Step 1: Write the failing test**

在 `crawler/tests/test_init_db_defaults.py` 新增索引断言：

```python
def _index_exists(conn, index_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = %s
            ) AS exists
            """,
            (index_name,),
        )
        row = cur.fetchone()
    return bool(row["exists"])


@pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
def test_vectors_embedding_hnsw_index_exists_after_init_db(self):
    conn = self.get_connection()
    try:
        self.init_db(conn)
        assert _index_exists(conn, "idx_vectors_embedding_hnsw")
    finally:
        conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd crawler && uv run pytest tests/test_init_db_defaults.py::TestInitDbTimestampDefaults::test_vectors_embedding_hnsw_index_exists_after_init_db -v`

Expected: FAIL，当前 `init_db` 未创建该索引。

**Step 3: Write minimal implementation**

在 `crawler/db.py` 的 `statements` 中新增：

```python
"CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw ON vectors USING hnsw (embedding vector_cosine_ops);",
```

并保持其在 `CREATE TABLE vectors` 之后执行。

**Step 4: Run test to verify it passes**

Run: `cd crawler && uv run pytest tests/test_init_db_defaults.py -v`

Expected: PASS（若本机未配置 DATABASE_URL，测试将 skip；至少保证无语法错误且测试可收敛）。

---

### Task 5: 修正文档 ai_end/migrations/README.md（表与索引描述对齐）

**Files:**
- Modify: `ai_end/migrations/README.md`
- Test: `ai_end/migrations/README.md`

**Step 1: Write the failing test**

先用文本契约检查确认现状不一致：

Run: `rg -n "documents|idx_documents_|user_id \| varchar\(64\)" ai_end/migrations/README.md`

Expected: 命中旧描述（FAIL 语义：文档未对齐）。

**Step 2: Run test to verify it fails**

Run: `rg -n "### documents|idx_documents_embedding|idx_documents_title_trgm" ai_end/migrations/README.md`

Expected: 输出匹配行，证明仍有错误内容。

**Step 3: Write minimal implementation**

按设计稿最小改动：

- 删除 `documents` 表段落，替换为 `articles` 的真实字段说明
- 删除 `idx_documents_*`，替换为 `idx_articles_published_on`、`idx_articles_title_trgm`、`idx_articles_content_trgm`
- 将 `conversations.user_id` 描述从 `VARCHAR(64)` 改为 `UUID`

建议替换示例片段：

```markdown
### articles（OA 文章表）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | bigint | PRIMARY KEY | 自增主键 |
| title | text | NOT NULL | 文章标题 |
| unit | text | | 发布单位 |
| link | text | UNIQUE NOT NULL | 文章链接 |
| published_on | date | NOT NULL | 发布日期 |
| content | text | NOT NULL | 正文 |
| summary | text | NOT NULL | 摘要 |
| attachments | jsonb | DEFAULT '[]' | 附件 |
```

**Step 4: Run test to verify it passes**

Run: `rg -n "documents|idx_documents_|user_id \| varchar\(64\)" ai_end/migrations/README.md`

Expected: 无输出（PASS 语义）。


---

### Task 6: 修正文档 CLAUDE.md 的不存在表项

**Files:**
- Modify: `CLAUDE.md`
- Test: `CLAUDE.md`

**Step 1: Write the failing test**

Run: `rg -n "messages.*聊天消息" CLAUDE.md`

Expected: 命中该行（FAIL 语义：文档存在错误条目）。

**Step 2: Run test to verify it fails**

Run: `rg -n "messages" CLAUDE.md`

Expected: 仍可命中。

**Step 3: Write minimal implementation**

删除不存在的 `messages` 表条目，并在 `conversations` 条目补充“消息存储于 `messages` JSONB 字段”。

建议替换为：

```markdown
- `conversations`: 会话记录 (user_id, conversation_id, title, messages JSONB)
```

**Step 4: Run test to verify it passes**

Run: `rg -n "messages.*聊天消息" CLAUDE.md`

Expected: 无输出（PASS 语义）。


---

### Task 7: 全量回归验证（合并前闸门）

**Files:**
- Verify: `backend/internal/model/*.go`
- Verify: `backend/internal/migration/*.go`
- Verify: `crawler/db.py`
- Verify: `crawler/tests/test_init_db_defaults.py`
- Verify: `ai_end/migrations/README.md`
- Verify: `CLAUDE.md`

**Step 1: Write the failing test**

先跑一次跨模块验证，确认是否仍有失败点：

Run: `cd backend && go test ./internal/model ./internal/migration -v`

Expected: 若有遗漏，应出现 FAIL（先暴露问题再收敛）。

**Step 2: Run test to verify it fails**

Run: `cd crawler && uv run pytest tests/test_init_db_defaults.py -v`

Expected: 在有数据库环境下全部通过；无数据库时为 skip，不应出现语法失败。

**Step 3: Write minimal implementation**

根据失败信息做最小修复，仅限本计划文件清单，不扩大范围。

**Step 4: Run test to verify it passes**

Run:

```bash
cd backend && go test ./internal/model ./internal/migration -v
cd ../crawler && uv run pytest tests/test_init_db_defaults.py -v
cd .. && rg -n "documents|idx_documents_|messages.*聊天消息|user_id \| varchar\(64\)" ai_end/migrations/README.md CLAUDE.md
```

Expected:
- Go 测试 PASS
- crawler 测试 PASS/skip
- 文档关键字检查无输出

---

## 交付核对清单

- [ ] Article/Vector 的 `published_on` 均显式 `type:date`
- [ ] Conversation/ConversationSession/UserProfile 的 `ID` 已为 `uint32`
- [ ] 新迁移 `2026041001_shared_table_fk_constraints` 已注册并有测试覆盖
- [ ] crawler `init_db` 已补齐 `idx_vectors_embedding_hnsw`
- [ ] `ai_end/migrations/README.md` 不再出现 `documents` 与 `idx_documents_*`
- [ ] `CLAUDE.md` 不再声明不存在的 `messages` 表
- [ ] 回归命令执行结果已记录
