# AI End Skill 化重构设计

## 背景

将 `ai_end` 原有业务能力（向量检索、文章内容定位、回答组装）拆解为独立 skill 并迁移到 `ai_end_refactor`，同时彻底移除通用 `documents` 相关代码，统一为 `articles + vectors` 双表结构。

## 核心目标

1. 将业务能力 skill 化：向量检索、文章内容定位、回答组装
2. 继续沿用 `articles + vectors` 双表结构
3. 彻底移除 `documents` 相关测试、实现代码与迁移语句
4. 优先复用 `ai_end_refactor` 已有模块
5. 保证功能完整、逻辑清晰

## 约束

- **数据迁移策略**：仅改代码，不搬历史数据
- **表结构对齐**：核心定义与 `backend/db.py:31-60` 保持一致，允许扩展
- **命名策略**：`document-retrieval` → `article-retrieval`，工具名统一替换为 article 语义

---

## Section 1：数据层 — Migration SQL

### 删除内容

- `documents` 表 CREATE TABLE
- `idx_documents_embedding` (HNSW)
- `idx_documents_content_hash` (UNIQUE)
- `idx_documents_title_trgm` (GIN)
- `idx_documents_content_trgm` (GIN)
- `COMMENT ON TABLE documents ...`

### 新增内容

```sql
CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    unit TEXT,
    link TEXT NOT NULL UNIQUE,
    published_on DATE NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    attachments JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_published_on ON articles (published_on);
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_articles_content_trgm ON articles USING gin (content gin_trgm_ops);
COMMENT ON TABLE articles IS 'OA文章表';

CREATE TABLE IF NOT EXISTS vectors (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT REFERENCES articles(id) ON DELETE CASCADE,
    embedding vector(1024),
    published_on DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vectors_published_on ON vectors (published_on);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vectors_article ON vectors(article_id);
CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw ON vectors USING hnsw (embedding vector_cosine_ops);
COMMENT ON TABLE vectors IS '文章向量表';
```

### 保留不变

`skills`、`skill_references`、`conversations`、`conversation_sessions`、`user_profiles` 表及其索引和注释，完全不动。

---

## Section 2：检索层 — ArticleRetriever

### 新增 `ArticleRetriever` 类

继承 `BaseRetriever`，覆写 `_vector_search`，核心 SQL 改为 JOIN 查询：

```sql
SELECT v.id, a.title, a.unit, a.published_on, a.summary
FROM vectors v
JOIN articles a ON v.article_id = a.id
ORDER BY v.embedding <=> $1
LIMIT $2;
```

### 与 DocumentRetriever 的关键差异

| 维度 | DocumentRetriever | ArticleRetriever |
|------|-------------------|-----------------|
| 向量搜索 | 单表 `documents` | JOIN `vectors + articles` |
| 返回字段 | id, title, summary, created_at | id, title, unit, published_on, summary |
| 关键词搜索 | pg_trgm on `documents` | pg_trgm on `articles` |
| 排序 | 仅 similarity + rerank | similarity + 时间衰减 + rerank |
| detail_level | 不支持 | 支持 brief/full |

### 时间衰减融合

在 rerank 之后、返回之前，对结果做时间衰减重排：

```python
score = rerank_score - recency_weight * exp(-days_since_publish / half_life_days)
```

- 默认 `recency_weight=0`（可通过配置开启）
- `half_life_days` 默认 30 天
- 当 `recency_weight=0` 时完全退化为纯 rerank 排序，零额外开销

### ContentFetcher 适配

`ContentFetcher.get()` 的 SQL 改为：

```sql
SELECT title, content FROM articles WHERE id = $1
```

### search_articles 的 detail_level 参数

- `brief`（默认）：返回 title + summary
- `full`：返回 title + summary + content

### 文件变更

| 文件 | 操作 |
|------|------|
| `src/core/article_retrieval.py` | **新建** — ArticleRetriever + search_articles/grep_article/grep_articles |
| `src/core/base_retrieval.py` | **不变** |
| `src/core/document_content.py` | **改** — ContentFetcher SQL 改查 articles 表 |
| `src/core/document_retrieval.py` | **删除** |

---

## Section 3：回答组装层 — ResponseComposer

### 新增 `ResponseComposer` 类

```
ResponseComposer
├── compose(query, context_documents, detail_level) → str
└── _format_sources(context_documents) → str
```

**职责**：
1. 接收检索结果（`context_documents`）和用户原始 query
2. 组装 LLM prompt（system prompt + context + query）
3. 调用 LLM 生成回答
4. 返回最终回答文本

### compose 数据流

```
用户问题 + 检索结果 → 构建 context block → 拼装 prompt → LLM 调用 → 返回回答
```

### context block 格式

```
[文章1] 标题: xxx
发布单位: xxx
发布日期: xxx
摘要: xxx
内容: xxx  (仅 detail_level=full 时)
---
[文章2] ...
```

### format_sources 格式

```
来源:
- 《文章标题》 (发布单位, 发布日期)
```

### 与 article-retrieval skill 的集成

`article-retrieval` skill 注册时挂载：
- `search_articles` 工具（ArticleRetriever）
- `grep_article` / `grep_articles` 工具（ArticleRetriever 关键词搜索）
- ResponseComposer 作为 skill 内部依赖

### 文件变更

| 文件 | 操作 |
|------|------|
| `src/core/response_composer.py` | **新建** — ResponseComposer 类 |
| `src/skills/article-retrieval/` | **改** — skill prompt 中集成 compose 指导 |
| `src/core/rag_chain.py` | **保留但精简** — 仅保留 LLM 调用基础设施 |

---

## Section 4：测试层清理与重构

### 删除的测试

| 文件/内容 | 操作 |
|-----------|------|
| `tests/**/test_document*.py` | **删除** |
| `tests/fixtures/**/document*.py` | **删除** |
| `conftest.py` 中 document 相关 fixture | **删除** |
| migration SQL 测试中 documents 断言 | **改** → articles + vectors |

### 新增的测试

| 文件 | 覆盖范围 |
|------|----------|
| `tests/core/test_article_retrieval.py` | 向量搜索、关键词搜索、时间衰减 |
| `tests/core/test_response_composer.py` | context 格式化、compose 拼装、source 引用 |
| `tests/skills/test_article_retrieval_skill.py` | 工具注册、prompt 校验 |

### 需修改的测试

| 文件 | 修改内容 |
|------|----------|
| `tests/core/test_document_content.py` | **重命名** → `test_article_content.py`，SQL 断言改查 articles |
| `tests/conftest.py` | 删除 document fixture，新增 article/vector fixture |
| 引用 `DocumentRetriever` 的测试 | 替换为 `ArticleRetriever` |

### Fixture 设计

```python
@pytest.fixture
def sample_article():
    return {
        "id": 1,
        "title": "关于期末考试安排的通知",
        "unit": "教务处",
        "link": "http://oa.example.com/1",
        "published_on": date(2026, 3, 20),
        "content": "根据学校安排...",
        "summary": "期末考试将于6月举行",
        "attachments": []
    }

@pytest.fixture
def sample_vector(sample_article):
    return {
        "id": 1,
        "article_id": 1,
        "embedding": [0.1] * 1024,
        "published_on": date(2026, 3, 20)
    }
```

---

## Section 5：Skill 注册与配置清理

### Skill 注册变更

| 变更项 | 旧值 | 新值 |
|--------|------|------|
| skill 名称 | `document-retrieval` | `article-retrieval` |
| skill 目录 | `src/skills/document-retrieval/` | `src/skills/article-retrieval/` |
| 工具名 | `search_documents`, `grep_document`, `grep_documents` | `search_articles`, `grep_article`, `grep_articles` |

### 配置文件清理

| 文件 | 操作 |
|------|------|
| `src/core/config.py` | 删除 documents 配置，新增 articles 配置 |
| `src/core/document_retrieval.py` | **删除** |
| `src/skills/document-retrieval/` | **删除整个目录** |
| `.env.example` | 移除 document 变量，补充 article 变量 |
| `pyproject.toml` | 如有 document 入口，同步修改 |

### 导入路径清理

全项目搜索并替换：
- `from src.core.document_retrieval import ...` → 删除或替换为 `from src.core.article_retrieval import ...`
- `from src.skills.document_retrieval import ...` → `from src.skills.article_retrieval import ...`
- `DocumentRetriever` → `ArticleRetriever`
- `ContentFetcher` 中 `documents` 表名 → `articles`

---

## 验收标准

1. **全量测试通过**：`pytest` 零失败，无 document 相关残留引用
2. **Grep 干净**：`grep -r "document" src/ tests/ --include="*.py"` 无业务相关命中
3. **Migration 幂等**：SQL 可重复执行不报错
4. **Skill 可用**：`article-retrieval` skill 正确注册，agent 可调用三个工具
5. **向量搜索可用**：ArticleRetriever 能正确执行 JOIN 查询并返回文章数据
6. **回答组装可用**：ResponseComposer 能正确格式化 context 并调用 LLM 生成回答
