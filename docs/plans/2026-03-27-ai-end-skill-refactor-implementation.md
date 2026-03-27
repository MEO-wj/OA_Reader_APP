# AI End Skill 化重构 — 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `ai_end_refactor` 的通用 documents 检索体系替换为 OA 文章专用的 articles+vectors 双表结构，并将业务能力 skill 化为 `article-retrieval`。

**Architecture:** 继承 `BaseRetriever` 创建 `ArticleRetriever`（JOIN 查询 vectors+articles），新增 `ResponseComposer` 封装回答组装逻辑，新建 `article-retrieval` skill 替代 `document-retrieval`。彻底移除 documents 全链路。

**Tech Stack:** Python 3.11+, asyncpg, pgvector, OpenAI API (Embedding + Rerank), pytest

---

### Task 1: Migration SQL — 替换 documents 为 articles+vectors

**Files:**
- Modify: `ai_end_refactor/migrations/001_init_generic_backend.sql`

**Step 1: 备份并修改 migration SQL**

删除第 10-38 行（documents 建表 + 4 个索引），替换为 articles+vectors 双表定义：

```sql
-- OA 文章表
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

-- 文章向量表
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

同时将第 111 行的 `COMMENT ON TABLE documents` 替换为上述两个 COMMENT。

**Step 2: 验证 SQL 语法正确**

确认保留不变的内容：`skills`、`skill_references`、`conversations`、`conversation_sessions`、`user_profiles` 表及其索引和注释。



---

### Task 2: migrate.py — 更新 schema drift 检测和修复

**Files:**
- Modify: `ai_end_refactor/migrations/migrate.py:35-86` (_has_schema_drift)
- Modify: `ai_end_refactor/migrations/migrate.py:89-195` (_apply_schema_repair)
- Modify: `ai_end_refactor/migrations/migrate.py:263-355` (验证输出部分)

**Step 1: 更新 `_has_schema_drift` 的 checks 列表**

将 documents 相关的 6 项检查：
```python
("documents", "id"),
("documents", "title"),
("documents", "content"),
("documents", "summary"),
("documents", "embedding"),
("documents", "content_hash"),
```
替换为：
```python
("articles", "id"),
("articles", "title"),
("articles", "content"),
("articles", "summary"),
("vectors", "id"),
("vectors", "article_id"),
("vectors", "embedding"),
```

**Step 2: 更新 `_apply_schema_repair` 的 repair_sql_list**

删除 documents 建表及 4 个索引的 repair SQL，替换为 articles+vectors 的 IF NOT EXISTS 建表 SQL（与 Task 1 的 SQL 保持一致）。

**Step 3: 更新验证输出**

将 `run_migration` 中所有 `'documents'` 引用（表结构验证、索引验证、注释验证）替换为 `'articles'`。将验证 SQL 中的 `tablename = 'documents'` 改为 `tablename IN ('articles', 'vectors')`。

**Step 4: 运行现有测试确认基础不退化**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_migrate.py -v`
Expected: 目前这些测试会因为文档改动而失败（这是预期的，后续 Task 会修复测试）



---

### Task 3: test_migrate.py — 更新迁移测试

**Files:**
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:192-228` (test_schema_drift_check_targets_generic_tables)
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:243-253` (test_apply_schema_repair_adds_documents_content_trgm_index)
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:256-266` (test_apply_schema_repair_adds_documents_embedding_index)
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:269-278` (test_apply_schema_repair_adds_documents_content_hash_index)
- Modify: `ai_end_refactor/tests/unit/test_migrate.py:281-288` (test_baseline_migration_contains_documents_content_trgm_index)

**Step 1: 更新 test_schema_drift_check_targets_generic_tables**

将 expected_generic_tables 中的 `"documents"` 替换为 `"articles"` 和 `"vectors"`，并更新列集合：
```python
expected_generic_tables = {
    "articles": ["id", "title", "content", "summary"],
    "vectors": ["id", "article_id", "embedding"],
    "skills": ["id", "name", "description", "verification_token"],
    # ...其余不变
}
```

**Step 2: 更新/删除 documents 索引相关的 3 个 repair 测试**

- `test_apply_schema_repair_adds_documents_content_trgm_index` → 改为验证 `idx_articles_content_trgm`
- `test_apply_schema_repair_adds_documents_embedding_index` → 改为验证 `idx_vectors_embedding_hnsw`
- `test_apply_schema_repair_adds_documents_content_hash_index` → 删除（articles 无 content_hash）或改为验证 `idx_vectors_article`

**Step 3: 更新基线测试**

`test_baseline_migration_contains_documents_content_trgm_index` → 改为验证 articles content trgm 索引。

**Step 4: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_migrate.py -v`
Expected: ALL PASS

---

### Task 4: verify_table.py — 更新表验证脚本

**Files:**
- Modify: `ai_end_refactor/migrations/verify_table.py`
- Modify: `ai_end_refactor/tests/unit/test_verify_table.py`

**Step 1: 更新 verify_table.py**

将所有 `'documents'::regclass` 替换为 `'articles'::regclass`，将输出文案改为 "验证 articles 表结构"。同时新增 vectors 表的索引验证。

**Step 2: 更新 test_verify_table.py**

`test_verify_table_targets_documents_schema` → 改为验证 `articles`：
```python
def test_verify_table_targets_articles_schema():
    source = inspect.getsource(verify_table.verify_table).lower()
    assert "articles" in source
    assert "documents" not in source
```

**Step 3: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_verify_table.py -v`
Expected: ALL PASS


---

### Task 5: ContentFetcher — SQL 改查 articles 表

**Files:**
- Modify: `ai_end_refactor/src/core/document_content.py:74` (SQL query)
- Modify: `ai_end_refactor/tests/unit/test_document_content.py:152-164` (test_content_fetcher_queries_documents_table)

**Step 1: 写失败测试 — 验证 ContentFetcher 查询 articles 表**

修改 `test_content_fetcher_queries_documents_table` → 重命名为 `test_content_fetcher_queries_articles_table`，断言改为 `"articles" in query.lower()`。

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_document_content.py::test_content_fetcher_queries_documents_table -v`
Expected: FAIL (query 中仍是 "documents")

**Step 2: 修改 ContentFetcher.get() SQL**

`document_content.py:74` 的 SQL 从：
```sql
SELECT title, content FROM documents WHERE id = $1
```
改为：
```sql
SELECT title, content FROM articles WHERE id = $1
```

**Step 3: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_document_content.py -v`
Expected: ALL PASS

---

### Task 6: ArticleRetriever — TDD 实现核心检索类

**Files:**
- Create: `ai_end_refactor/src/core/article_retrieval.py`
- Create: `ai_end_refactor/tests/unit/test_article_retrieval.py`

**Step 1: 写失败测试 — ArticleRetriever 基本结构**

```python
# tests/unit/test_article_retrieval.py
"""article_retrieval 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class AsyncContextManager:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj
    async def __aenter__(self):
        return self.mock_obj
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPool:
    def __init__(self, conn):
        self._conn = conn
    def acquire(self):
        return AsyncContextManager(self._conn)


def test_article_retrieever_exists():
    """ArticleRetriever 类应存在且可实例化。"""
    from src.core.article_retrieval import ArticleRetriever
    retriever = ArticleRetriever()
    assert retriever is not None


def test_article_retriever_extends_base():
    """ArticleRetriever 应继承 BaseRetriever。"""
    from src.core.article_retrieval import ArticleRetriever
    from src.core.base_retrieval import BaseRetriever
    assert issubclass(ArticleRetriever, BaseRetriever)


def test_article_retriever_uses_vectors_table():
    """ArticleRetriever 应使用 vectors 表作为向量搜索的目标。"""
    from src.core.article_retrieval import ArticleRetriever
    retriever = ArticleRetriever()
    # 向量搜索目标表应是 vectors
    assert "vectors" in retriever.table_name


def test_search_articles_function_exists():
    """search_articles 顶层函数应存在。"""
    from src.core.article_retrieval import search_articles
    assert callable(search_articles)


def test_grep_article_function_exists():
    """grep_article 顶层函数应存在。"""
    from src.core.article_retrieval import grep_article
    assert callable(grep_article)


def test_grep_articles_function_exists():
    """grep_articles 顶层函数应存在。"""
    from src.core.article_retrieval import grep_articles
    assert callable(grep_articles)
```

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_article_retrieval.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 2: 创建 ArticleRetriever 最小实现**

创建 `ai_end_refactor/src/core/article_retrieval.py`：

```python
"""文章检索模块

提供 OA 文章的向量搜索、关键词搜索和内容定位功能。
"""

from __future__ import annotations

import re
from typing import Any

from src.config.settings import Config
from src.core.api_clients import get_embedding_client, get_rerank_client
from src.core.api_queue import get_api_queue
from src.core.base_retrieval import BaseRetriever, generate_embedding
from src.core.db import get_pool
from src.core.document_content import (
    ContentFetcher,
    KeywordMatcher,
    LineRangeMatcher,
    Matcher,
    RegexMatcher,
    ResultFormatter,
    SectionMatcher,
)


def _is_transient_db_error(error: Exception) -> bool:
    message = str(error).lower()
    markers = (
        "connection was closed",
        "another operation is in progress",
        "connection is closed",
    )
    return any(marker in message for marker in markers)


def _get_embedding_client():
    return get_embedding_client()


def _get_rerank_client():
    return get_rerank_client()


def _rerank_documents_sync(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """同步调用 Rerank API 对候选文章重新排序。"""
    if not candidates:
        return []
    if top_k is None:
        top_k = len(candidates)

    config = Config.load()
    client = _get_rerank_client()

    documents = []
    for doc in candidates:
        text_parts = []
        if "title" in doc and doc["title"]:
            text_parts.append(doc["title"])
        if "summary" in doc and doc["summary"]:
            text_parts.append(doc["summary"])
        documents.append("\n".join(text_parts) if text_parts else str(doc.get("id", "")))

    try:
        response = client.responses.create(
            model=config.rerank_model,
            query=query,
            documents=documents,
            top_k=top_k,
        )

        id_map = {i: doc for i, doc in enumerate(candidates)}
        results = []

        if hasattr(response, "results") and response.results:
            for item in sorted(response.results, key=lambda x: x.relevance_score, reverse=True):
                idx = item.index
                if idx in id_map:
                    doc = id_map[idx].copy()
                    doc["rerank_score"] = item.relevance_score
                    results.append(doc)

        if not results:
            return candidates
        return results
    except Exception as e:
        raise RuntimeError(f"Rerank API 调用失败: {str(e)}") from e


async def _rerank_documents(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    try:
        return await get_api_queue().submit("rerank", _rerank_documents_sync, query, candidates, top_k)
    except Exception:
        return candidates


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except Exception:
        return getattr(row, key, default)


class ArticleRetriever(BaseRetriever):
    """OA 文章检索器，使用 vectors + articles JOIN 查询。"""

    def __init__(self):
        super().__init__(
            table_name="vectors",
            select_columns=["v.id", "a.title", "a.unit", "a.published_on", "a.summary"],
            embedding_column="embedding",
            get_pool_fn=get_pool,
            rerank_fn=_rerank_documents,
            is_transient_error=_is_transient_db_error,
        )

    async def _build_metadata_filter(
        self,
        start_index: int = 1,
        **filters: Any,
    ) -> tuple[str, list[Any]]:
        return "", []

    async def _vector_search(
        self,
        query_embedding_str: str,
        limit: int = 20,
        threshold: float = 0.5,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """覆写基类：使用 JOIN 查询 vectors + articles。"""
        params: list[Any] = [query_embedding_str, threshold]
        where_clauses = [
            "v.embedding IS NOT NULL",
            f"1 - (v.embedding <=> $1::vector) >= $2",
        ]

        if metadata_filters:
            filter_clause, filter_params = await self._build_metadata_filter(
                start_index=3, **metadata_filters,
            )
            if filter_clause:
                where_clauses.append(f"({filter_clause})")
                params.extend(filter_params)

        params.append(limit)
        limit_idx = len(params)

        sql = """
            SELECT v.id, a.title, a.unit, a.published_on, a.summary,
                   1 - (v.embedding <=> $1::vector) as similarity
            FROM vectors v
            JOIN articles a ON v.article_id = a.id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY v.embedding <=> $1::vector
            LIMIT ${limit_idx}
        """

        import asyncio
        last_error: Exception | None = None
        for attempt in range(self._retry_attempts):
            try:
                pool = await self._get_pool_fn()
                async with pool.acquire() as conn:
                    rows = await conn.fetch(sql, *params)
                return list(rows)
            except Exception as exc:
                last_error = exc
                transient = self._is_transient_error(exc) if self._is_transient_error else False
                if transient and attempt < self._retry_attempts - 1:
                    await asyncio.sleep(self._retry_backoff)
                    continue
                break

        if last_error is not None and self._is_transient_error and self._is_transient_error(last_error):
            raise RuntimeError("TRANSIENT_DB_ERROR") from last_error
        if last_error is not None:
            raise last_error
        return []

    async def search_articles(
        self,
        query: str,
        keywords: str | None = None,
        top_k: int = 10,
        threshold: float = 0.5,
    ) -> dict[str, Any]:
        """三层检索策略搜索相关文章。"""
        if not query or not query.strip():
            raise ValueError("查询文本不能为空")

        try:
            query_embedding = await generate_embedding(query)
            query_embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        except Exception as exc:
            return {"error": f"搜索失败: {str(exc)}", "results": []}

        try:
            ebd_rows = await self._vector_search(
                query_embedding_str=query_embedding_str,
                limit=20,
                threshold=threshold,
            )
        except RuntimeError as exc:
            if str(exc) == "TRANSIENT_DB_ERROR":
                return {"error": "搜索失败: 临时数据库连接异常，请稍后重试", "results": []}
            return {"error": f"搜索失败: {str(exc)}", "results": []}
        except Exception as exc:
            return {"error": f"搜索失败: {str(exc)}", "results": []}

        ebd_results: dict[int, dict[str, Any]] = {}
        for row in ebd_rows:
            row_id = _row_value(row, "id")
            ebd_results[row_id] = {
                "id": row_id,
                "title": _row_value(row, "title"),
                "unit": _row_value(row, "unit"),
                "published_on": str(_row_value(row, "published_on", "")),
                "summary": _row_value(row, "summary"),
                "ebd_similarity": float(_row_value(row, "similarity", 0.0)),
                "keyword_similarity": None,
            }

        keyword_results: dict[int, dict[str, Any]] = {}
        if keywords:
            try:
                pool = await get_pool()
                kw_rows = await _search_by_keywords(keywords, pool, limit=20)
                for row in kw_rows:
                    doc_id = row["id"]
                    if doc_id in keyword_results:
                        if row["keyword_similarity"] > keyword_results[doc_id]["keyword_similarity"]:
                            keyword_results[doc_id]["keyword_similarity"] = row["keyword_similarity"]
                    else:
                        keyword_results[doc_id] = {
                            "id": row["id"],
                            "title": row["title"],
                            "unit": row.get("unit"),
                            "published_on": str(row.get("published_on", "")),
                            "summary": row["summary"],
                            "ebd_similarity": None,
                            "keyword_similarity": row["keyword_similarity"],
                        }
            except Exception:
                pass

        candidates = _merge_results(ebd_results, keyword_results)
        reranked_results = await self._rerank(query, candidates, top_k)

        formatted_results = []
        for doc in reranked_results[:top_k]:
            formatted_results.append({
                "id": doc["id"],
                "title": doc["title"],
                "unit": doc.get("unit"),
                "published_on": doc.get("published_on"),
                "summary": doc["summary"],
                "ebd_similarity": doc.get("ebd_similarity"),
                "keyword_similarity": doc.get("keyword_similarity"),
                "rerank_score": doc.get("rerank_score"),
            })
        return {"results": formatted_results}


async def _search_by_keywords(
    keywords: str,
    pool,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """使用 pg_trgm 进行关键词模糊搜索（查 articles 表）。"""
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        return []

    results = []
    async with pool.acquire() as conn:
        for keyword in keyword_list:
            rows = await conn.fetch("""
                SELECT id, title, unit, published_on, summary,
                       GREATEST(
                           similarity(title, $2),
                           similarity(content, $2)
                       ) as similarity
                FROM articles
                WHERE title % $2 OR content % $2
                ORDER BY similarity DESC
                LIMIT $1
            """, limit, keyword)

            for row in rows:
                results.append({
                    "id": row["id"],
                    "title": row["title"],
                    "unit": row.get("unit"),
                    "published_on": str(row.get("published_on", "")),
                    "summary": row["summary"],
                    "keyword_similarity": float(row["similarity"]),
                    "matched_keyword": keyword,
                })

    return results


def _merge_results(
    ebd_results: dict[int, dict[str, Any]],
    keyword_results: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    all_docs: dict[int, dict[str, Any]] = {}
    for doc_id, result in ebd_results.items():
        all_docs[doc_id] = result.copy()
    for doc_id, kw_result in keyword_results.items():
        if doc_id in all_docs:
            all_docs[doc_id]["keyword_similarity"] = kw_result["keyword_similarity"]
        else:
            all_docs[doc_id] = kw_result
    return list(all_docs.values())


def _detect_mode(
    keyword: str | None,
    section: str | None,
    pattern: str | None,
    start_line: int | None,
) -> str:
    if pattern:
        return "regex"
    if start_line is not None:
        return "line_range"
    if section:
        return "section"
    if keyword:
        return "keyword"
    return "summary"


def _get_matcher(mode: str) -> Matcher:
    matchers: dict[str, Matcher] = {
        "keyword": KeywordMatcher(),
        "regex": RegexMatcher(),
        "section": SectionMatcher(),
        "line_range": LineRangeMatcher(),
    }
    if mode not in matchers:
        raise ValueError(f"Unknown mode: {mode}")
    return matchers[mode]


def _split_keyword_terms(keyword: str | None) -> list[str]:
    if not keyword:
        return []
    parts = re.split(r"[,\uFF0C|]", keyword)
    terms = [part.strip() for part in parts if part and part.strip()]
    if not terms:
        return []
    return list(dict.fromkeys(terms))


async def _match_keyword_or(
    content: str,
    terms: list[str],
    context_lines: int,
    max_results: int,
) -> list[Any]:
    matcher = KeywordMatcher()
    merged = []
    seen: set[tuple[int, str]] = set()
    for term in terms:
        partial = await matcher.match(
            content, keyword=term, context_lines=context_lines, max_results=max_results,
        )
        for item in partial:
            key = (item.line_number, item.content)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_results:
                return merged
    return merged


async def grep_article(
    article_id: int,
    keyword: str | None = None,
    section: str | None = None,
    mode: str = "auto",
    context_lines: int = 0,
    max_results: int = 3,
    pattern: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """获取指定文章的具体内容。"""
    try:
        fetcher = ContentFetcher()
        fetched = await fetcher.get(article_id)
        if fetched is None:
            return ResultFormatter.not_found(f"文章 {article_id} 不存在")
        title, content = fetched

        current_mode = _detect_mode(keyword, section, pattern, start_line) if mode == "auto" else mode
        if current_mode == "summary":
            summary = content[:500] + "..." if len(content) > 500 else content
            return ResultFormatter.success(
                data={
                    "title": title,
                    "matches": [
                        {
                            "content": summary,
                            "line_number": 1,
                            "context_before": [],
                            "context_after": [],
                            "highlight_ranges": [],
                        }
                    ],
                },
                metadata={"total_matches": 1, "search_mode": "summary"},
            )

        try:
            matcher = _get_matcher(current_mode)
        except ValueError as exc:
            return ResultFormatter.error(str(exc))

        kwargs: dict[str, Any] = {"context_lines": context_lines}
        effective_mode = current_mode
        if current_mode == "keyword":
            terms = _split_keyword_terms(keyword)
            if len(terms) > 1:
                matches = await _match_keyword_or(content, terms, context_lines, max_results)
                effective_mode = "keyword_or"
                if not matches:
                    pattern_for_fallback = "|".join(re.escape(term) for term in terms)
                    regex_matcher = RegexMatcher()
                    matches = await regex_matcher.match(
                        content, pattern=pattern_for_fallback, context_lines=context_lines,
                    )
                    matches = matches[:max_results]
                    if matches:
                        effective_mode = "keyword_or_regex_fallback"
            else:
                kwargs["keyword"] = terms[0] if terms else keyword
                kwargs["max_results"] = max_results
                matcher = _get_matcher(current_mode)
                matches = await matcher.match(content, **kwargs)
        elif current_mode == "regex":
            kwargs["pattern"] = pattern
            matches = await matcher.match(content, **kwargs)
        elif current_mode == "section":
            kwargs["section"] = section
            matches = await matcher.match(content, **kwargs)
        elif current_mode == "line_range":
            kwargs["start_line"] = start_line
            kwargs["end_line"] = end_line
            matches = await matcher.match(content, **kwargs)
        else:
            matches = await matcher.match(content, **kwargs)

        if not matches:
            if current_mode == "keyword":
                return ResultFormatter.not_found(
                    f"未找到关键词 '{keyword}'",
                    metadata={"search_mode": effective_mode},
                )
            if current_mode == "section":
                return ResultFormatter.not_found(
                    f"未找到章节 '{section}'",
                    metadata={"search_mode": current_mode},
                )
            return ResultFormatter.not_found("未找到匹配内容", metadata={"search_mode": current_mode})

        formatted_matches = [
            {
                "content": item.content,
                "line_number": item.line_number,
                "context_before": item.context_before,
                "context_after": item.context_after,
                "highlight_ranges": item.highlight_ranges,
            }
            for item in matches
        ]
        return ResultFormatter.success(
            data={"title": title, "matches": formatted_matches},
            metadata={"total_matches": len(formatted_matches), "search_mode": effective_mode},
        )
    except Exception as exc:
        return ResultFormatter.error(f"获取文章失败: {str(exc)}")


async def grep_articles(
    article_ids: list[int],
    keyword: str | None = None,
    section: str | None = None,
    mode: str = "auto",
    context_lines: int = 0,
    max_results: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """跨多个文章搜索。"""
    results: list[dict[str, Any]] = []
    articles_with_matches = 0

    for article_id in article_ids:
        single = await grep_article(
            article_id=article_id,
            keyword=keyword,
            section=section,
            mode=mode,
            context_lines=context_lines,
            max_results=max_results,
            **kwargs,
        )
        if single.get("status") == "success":
            articles_with_matches += 1
            data = single.get("data", {})
            results.append(
                {
                    "article_id": article_id,
                    "title": data.get("title"),
                    "matches": data.get("matches", []),
                }
            )

    return ResultFormatter.success(
        data={"results": results},
        metadata={
            "total_articles": len(article_ids),
            "articles_with_matches": articles_with_matches,
            "search_mode": mode,
        },
    )


async def search_articles(
    query: str,
    keywords: str | None = None,
    top_k: int = 10,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """兼容旧接口：转发到 ArticleRetriever。"""
    retriever = ArticleRetriever()
    return await retriever.search_articles(
        query=query,
        keywords=keywords,
        top_k=top_k,
        threshold=threshold,
    )


async def close_resources():
    """关闭检索模块的资源。"""
    import asyncio
    from src.core.api_clients import close_clients
    await asyncio.get_event_loop().run_in_executor(None, close_clients)
```

**Step 3: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_article_retrieval.py -v`
Expected: ALL PASS

**Step 4: 补充 search_articles 核心测试（从 test_document_retrieval 迁移）**

在 `test_article_retrieval.py` 中补充以下测试（参考现有 `test_document_retrieval.py` 的模式，但使用 `article_retrieval` 模块和 articles 语义）：

- `test_search_articles_no_results` — 空结果
- `test_search_articles_with_threshold` — 高阈值过滤
- `test_search_articles_empty_query` — 空查询异常
- `test_search_articles_with_keywords_layer2` — 关键词搜索
- `test_search_articles_merged_results` — 去重
- `test_search_articles_rerank_scoring` — rerank 排序

每个测试的 mock 路径改为 `src.core.article_retrieval`，字段改为包含 `unit`、`published_on`。

**Step 5: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_article_retrieval.py -v`
Expected: ALL PASS

---

### Task 7: ResponseComposer — TDD 实现回答组装

**Files:**
- Create: `ai_end_refactor/src/core/response_composer.py`
- Create: `ai_end_refactor/tests/unit/test_response_composer.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_response_composer.py
"""response_composer 单元测试"""
import pytest


def test_format_context_block_basic():
    """应将文章列表格式化为 context block。"""
    from src.core.response_composer import ResponseComposer

    articles = [
        {"title": "文章A", "unit": "教务处", "published_on": "2026-03-20", "summary": "摘要A", "content": "内容A"},
        {"title": "文章B", "unit": "学工处", "published_on": "2026-03-15", "summary": "摘要B", "content": "内容B"},
    ]

    result = ResponseComposer.format_context_block(articles, detail_level="brief")

    assert "[文章1]" in result
    assert "文章A" in result
    assert "教务处" in result
    assert "2026-03-20" in result
    assert "摘要A" in result
    assert "内容A" not in result  # brief 模式不包含 content


def test_format_context_block_full_includes_content():
    """full 模式应包含文章内容。"""
    from src.core.response_composer import ResponseComposer

    articles = [
        {"title": "文章A", "unit": "教务处", "published_on": "2026-03-20", "summary": "摘要A", "content": "完整内容"},
    ]

    result = ResponseComposer.format_context_block(articles, detail_level="full")

    assert "完整内容" in result


def test_format_sources():
    """应格式化来源引用列表。"""
    from src.core.response_composer import ResponseComposer

    articles = [
        {"title": "文章A", "unit": "教务处", "published_on": "2026-03-20"},
        {"title": "文章B", "unit": "学工处", "published_on": "2026-03-15"},
    ]

    result = ResponseComposer.format_sources(articles)

    assert "来源:" in result
    assert "《文章A》" in result
    assert "教务处" in result
    assert "2026-03-20" in result


def test_format_sources_empty():
    """空列表应返回空字符串。"""
    from src.core.response_composer import ResponseComposer

    result = ResponseComposer.format_sources([])
    assert result == ""
```

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_response_composer.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 2: 创建 ResponseComposer 实现**

```python
# ai_end_refactor/src/core/response_composer.py
"""回答组装模块

将检索到的文章上下文组装为 LLM 可消费的 prompt，并格式化来源引用。
"""
from __future__ import annotations

from typing import Any


class ResponseComposer:
    """将检索结果组装为最终回答。"""

    @staticmethod
    def format_context_block(
        articles: list[dict[str, Any]],
        detail_level: str = "brief",
    ) -> str:
        """将文章列表格式化为 context block。"""
        if not articles:
            return ""

        blocks = []
        for i, article in enumerate(articles, 1):
            block = (
                f"[文章{i}] 标题: {article.get('title', '')}\n"
                f"发布单位: {article.get('unit', '未知')}\n"
                f"发布日期: {article.get('published_on', '')}\n"
                f"摘要: {article.get('summary', '')}"
            )
            if detail_level == "full" and article.get("content"):
                block += f"\n内容: {article['content']}"
            blocks.append(block)

        return "\n---\n".join(blocks)

    @staticmethod
    def format_sources(articles: list[dict[str, Any]]) -> str:
        """格式化来源引用。"""
        if not articles:
            return ""

        lines = ["来源:"]
        for article in articles:
            title = article.get("title", "")
            unit = article.get("unit", "")
            date = article.get("published_on", "")
            lines.append(f"- 《{title}》 ({unit}, {date})")

        return "\n".join(lines)

    @staticmethod
    def compose(
        query: str,
        articles: list[dict[str, Any]],
        detail_level: str = "brief",
    ) -> str:
        """组装最终回答（context + sources）。"""
        context = ResponseComposer.format_context_block(articles, detail_level)
        sources = ResponseComposer.format_sources(articles)

        parts = []
        if context:
            parts.append(context)
        if sources:
            parts.append(sources)

        return "\n\n".join(parts)
```

**Step 3: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_response_composer.py -v`
Expected: ALL PASS


---

### Task 8: 创建 article-retrieval skill

**Files:**
- Create: `ai_end_refactor/skills/article-retrieval/SKILL.md`
- Create: `ai_end_refactor/skills/article-retrieval/TOOLS.md`

**Step 1: 创建 SKILL.md**

基于 `skills/document-retrieval/SKILL.md`，将 document 语义替换为 article 语义：

```markdown
---
name: article-retrieval
description: OA文章检索工具，支持向量搜索与内容定位。适用于在学校OA公告中查找事实依据、定位细节段落、或对比多篇文章的场景。
verification_token: ARTICLE-RETRIEVAL-OA-2026
---

# 使用场景

当用户需要从学校OA公告中查找通知、定位具体条款、或对比多篇文章时使用此技能。

## 典型触发

- "查找关于期末考试安排的通知"
- "定位请假制度里关于事假的规定"
- "对比两份通知在报到时间上的差异"
- "提取某个通知里的关键步骤"

# 可用工具

## search_articles

向量搜索相关文章，返回匹配文章的标题、发布单位和摘要。

**参数:**
- `query` (string, 必需): 搜索查询文本
- `keywords` (string, 可选): 关键词，逗号分隔
- `top_k` (integer, 可选): 返回结果数量，默认 10
- `threshold` (float, 可选): 相似度阈值，默认 0.5

## grep_article

获取指定文章的具体内容，支持多种搜索模式。

**参数:**
- `article_id` (integer, 必需): 文章 ID
- `mode` (string, 可选): 搜索模式 (auto/summary/keyword/regex/section/line_range)
- `keyword` (string, 可选): 关键词
- `section` (string, 可选): 章节标题
- `pattern` (string, 可选): 正则表达式
- `context_lines` (integer, 可选): 上下文行数
- `max_results` (integer, 可选): 最大结果数
- `start_line`/`end_line` (integer, 可选): 行范围

## grep_articles

跨多个文章搜索内容。

# 使用建议

1. **先搜索**：使用 `search_articles` 搜索相关文章
2. **看摘要**：根据返回摘要选择最相关文章
3. **取详情**：使用 `grep_article` 获取具体内容
4. **做对比**：使用 `grep_articles` 对比多个文章
5. **防幻觉约束**：若最终证据不足，需明确说明"当前证据不足以确认"，不要暴露工具名、参数、`status` 等中间检索细节

# 输出风格

- 清晰引用来源：根据《[文章标题]》（发布单位，发布日期）
- 摘要优先：先给结论，再展开细节
- 实用导向：强调对用户最有用的条款
```

**Step 2: 创建 TOOLS.md**

基于 `skills/document-retrieval/TOOLS.md`，将所有 `document` 替换为 `article`，`search_documents` → `search_articles`，`grep_document` → `grep_article`，`grep_documents` → `grep_articles`，handler 改为 `article_retrieval.xxx`。

**Step 3: 验证 skill 可被解析**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_skill_system.py -v`
Expected: 现有测试不应退化（新增的 skill 不影响现有 filesystem skill 测试）

---

### Task 9: 更新 handlers.py — 模块映射和工具名

**Files:**
- Modify: `ai_end_refactor/src/chat/handlers.py:96-99` (module_mappings)
- Modify: `ai_end_refactor/src/chat/handlers.py:196-211` (truncator 分发)

**Step 1: 更新 module_mappings**

将第 97 行的：
```python
"document_retrieval": "src.core.document_retrieval",
```
改为：
```python
"article_retrieval": "src.core.article_retrieval",
```

**Step 2: 更新 truncator 分发逻辑**

将第 196-211 行的 `search_documents` / `grep_document` 判断改为 `search_articles` / `grep_article`：

```python
if function_name == "search_articles":
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and "results" in parsed:
            content = json.dumps(truncate_search_documents_result(parsed), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        content = truncate_tool_output("generic", function_name, content)["content"]
elif function_name == "grep_article":
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and "status" in parsed:
            content = json.dumps(truncate_grep_document_result(parsed), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        content = truncate_tool_output("generic", function_name, content)["content"]
else:
    content = truncate_tool_output("generic", function_name, content)["content"]
```


---

### Task 10: 更新 context_truncator.py — 函数名保持兼容

**Files:**
- Modify: `ai_end_refactor/src/chat/context_truncator.py` (注释更新)

context_truncator.py 中的 `truncate_search_documents_result` 和 `truncate_grep_document_result` 函数名对 handler 是内部调用，不涉及用户可见语义。**保留函数名不变**，仅更新注释中的 `search_documents` / `grep_document` 引用为 `search_articles` / `grep_article`。

**Step 1: 更新注释**

将模块 docstring 和函数 docstring 中的 `search_documents` → `search_articles`，`grep_document` → `grep_article`。


---

### Task 11: 更新 test_handlers.py — 工具名替换

**Files:**
- Modify: `ai_end_refactor/tests/unit/test_handlers.py`

**Step 1: 更新测试中的工具名和模块引用**

- 第 284-285 行：`"policy-retrieval"` mock 中 `"handler": "document_retrieval.search_documents"` → `"article_retrieval.search_articles"`
- 第 291 行：`mock_tool_call.function.name = "search_documents"` → `"search_articles"`
- 第 396-399 行：同上
- 第 404 行：`"search_documents"` → `"search_articles"`
- 第 426-429 行：`"handler": "document_retrieval.grep_document"` → `"article_retrieval.grep_article"`
- 第 434 行：`"grep_document"` → `"grep_article"`

**Step 2: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_handlers.py -v`
Expected: ALL PASS


---

### Task 12: 更新 client.py 和 main.py — 引用替换

**Files:**
- Modify: `ai_end_refactor/src/chat/client.py:28` (import)
- Modify: `ai_end_refactor/src/chat/client.py:585-598` (tool name checks)
- Modify: `ai_end_refactor/src/api/main.py:17` (import_documents)
- Modify: `ai_end_refactor/src/api/main.py:26` (close_resources)
- Modify: `ai_end_refactor/src/api/main.py:55-58` (document import)

**Step 1: 更新 client.py**

- 第 28 行：`from src.core.document_retrieval import close_resources` → `from src.core.article_retrieval import close_resources`
- 第 585 行：`if tool_name == "search_documents"` → `"search_articles"`
- 第 598 行：`elif tool_name == "grep_document"` → `"grep_article"`

**Step 2: 更新 main.py**

- 第 26 行：`from src.core.document_retrieval import close_resources` → `from src.core.article_retrieval import close_resources`
- 第 17 行：删除 `from scripts.import_documents import main as import_documents_main`
- 第 55-58 行：删除 `import_documents_main(Path("docs"))` 的调用（或注释掉）


---

### Task 13: 删除 document_retrieval.py 和 document-retrieval skill

**Files:**
- Delete: `ai_end_refactor/src/core/document_retrieval.py`
- Delete: `ai_end_refactor/skills/document-retrieval/` (整个目录)

**Step 1: 删除文件**

```bash
rm ai_end_refactor/src/core/document_retrieval.py
rm -rf ai_end_refactor/skills/document-retrieval/
```

**Step 2: 运行测试检查引用断裂**

Run: `cd ai_end_refactor && uv run pytest tests/ -v --tb=short 2>&1 | head -100`
Expected: 部分测试可能因引用 `document_retrieval` 而失败，记录下失败的测试文件名


---

### Task 14: 删除 document 相关的脚本、服务和 API

**Files:**
- Delete: `ai_end_refactor/scripts/import_documents.py`
- Delete: `ai_end_refactor/src/api/document_service.py`
- Delete: `ai_end_refactor/templates/documents/` (整个目录)

**Step 1: 删除文件**

```bash
rm ai_end_refactor/scripts/import_documents.py
rm ai_end_refactor/src/api/document_service.py
rm -rf ai_end_refactor/templates/documents/
```

**Step 2: 更新 admin.py — 移除 document 路由**

在 `src/api/admin.py` 中：
- 删除 `from src.api.document_service import ...` 导入
- 删除 `get_template`、`get_template_example`、`upload_document`、`get_documents`、`delete_document_endpoint` 路由
- 删除 `TEMPLATES_DIR` 行（第 20 行）
- 删除相关的 Pydantic model（如果有的话）
- 保留 `router` 基础定义

**Step 3: 更新 import_decider.py — 移除 document 检测**

删除 `needs_document_import` 导入和调用，简化 `should_run_auto_import` 仅检查 skills。

**Step 4: 更新 import_probe.py — 移除 document 探测**

删除 `needs_document_import` 函数、`_compute_document_hash` 函数、`_check_hashes_exist` 调用。

---

### Task 15: 更新剩余测试文件

**Files:**
- Modify: `ai_end_refactor/tests/unit/test_document_content.py` (重命名 → test_article_content.py)
- Modify: `ai_end_refactor/tests/unit/test_import_documents.py` (删除)
- Modify: `ai_end_refactor/tests/unit/test_import_decider.py` (更新)
- Modify: `ai_end_refactor/tests/unit/test_import_probe.py` (更新)
- Modify: `ai_end_refactor/tests/unit/test_document_service.py` (删除)
- Modify: `ai_end_refactor/tests/api/test_admin.py` (更新)
- Modify: `ai_end_refactor/tests/integration/test_concurrency_regression.py` (更新引用)
- Modify: `ai_end_refactor/tests/integration/test_rerank_integration.py` (检查引用)

**Step 1: 重命名 test_document_content.py → test_article_content.py**

```bash
mv ai_end_refactor/tests/unit/test_document_content.py ai_end_refactor/tests/unit/test_article_content.py
```

更新文件内的模块 docstring 和测试函数注释。

**Step 2: 删除已移除功能的测试**

```bash
rm ai_end_refactor/tests/unit/test_import_documents.py
rm ai_end_refactor/tests/unit/test_document_service.py
```

**Step 3: 更新 test_import_decider.py 和 test_import_probe.py**

移除所有 `needs_document_import`、`document` 相关的测试用例。

**Step 4: 更新 test_admin.py**

移除所有 document 路由相关的测试用例（`test_get_documents_template`、`test_upload_document_success`、`test_get_documents`、`test_delete_document` 等）。

**Step 5: 更新 test_concurrency_regression.py**

第 16 行：`from src.core import document_retrieval` → `from src.core import article_retrieval`
第 49 行：`monkeypatch.setattr(document_retrieval, "get_pool", ...)` → 使用 `article_retrieval`
第 78 行：`document_retrieval.search_documents(...)` → `article_retrieval.search_articles(...)`

**Step 6: 更新 test_rerank_integration.py**

检查是否引用 `document_retrieval`，如有则替换为 `article_retrieval`。

**Step 7: 运行全量测试**

Run: `cd ai_end_refactor && uv run pytest tests/ -v --tb=short`
Expected: ALL PASS

---

### Task 16: 全局 grep 清理与最终验证

**Files:**
- 可能修改: 多个文件中的残留 `document` 引用

**Step 1: 全局搜索 document 残留**

Run:
```bash
cd ai_end_refactor && grep -rn "document" src/ tests/ --include="*.py" | grep -v "# " | grep -v "docstring" | grep -v ".md"
```

排除注释后，检查业务代码中是否仍有 `document` 残留。

**已知需要检查的残留：**
- `src/core/db_skill_system.py:266` — `"description": "技能名称，如 'document-retrieval' 或其他已激活技能"` → 改为 `'article-retrieval'`
- `src/core/skill_system.py:153` — 同上
- `src/core/hash_utils.py` — `normalize_document_content`、`compute_document_hash` — 函数名保留（仍可用于 articles），但确认无 `documents` 表引用

**Step 2: 修复残留引用**

逐个修复 Step 1 发现的残留。

**Step 3: 运行全量测试**

Run: `cd ai_end_refactor && uv run pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 4: 验收检查**

1. `grep -rn "document" src/ tests/ --include="*.py" | grep -v "docstring" | grep -v "hash" | wc -l` → 应为 0（或仅注释）
2. `grep -rn "DocumentRetriever" src/ tests/ --include="*.py"` → 应为 0
3. `grep -rn "documents" ai_end_refactor/migrations/001_init_generic_backend.sql` → 应为 0
4. `ls ai_end_refactor/skills/document-retrieval/ 2>/dev/null` → 应不存在
5. `ls ai_end_refactor/src/core/document_retrieval.py 2>/dev/null` → 应不存在
6. `ls ai_end_refactor/skills/article-retrieval/SKILL.md` → 应存在

---

### Task 17: 更新 CLAUDE.md — 反映新架构

**Files:**
- Modify: `ai_end_refactor/CLAUDE.md`

**Step 1: 更新检索系统架构说明**

将 "检索系统架构" 中的 document 语义替换为 article 语义。更新 handler 映射说明。更新常见排查命令。

---

## 验收标准清单

- [ ] `uv run pytest tests/` 全量通过
- [ ] `grep -rn "document" src/ tests/ --include="*.py"` 无业务相关命中
- [ ] `migrations/001_init_generic_backend.sql` 中无 `documents` 引用
- [ ] `skills/article-retrieval/SKILL.md` 存在且包含 `verification_token`
- [ ] `skills/article-retrieval/TOOLS.md` 中工具名均为 article 语义
- [ ] `src/core/article_retrieval.py` 中 `ArticleRetriever` 使用 JOIN 查询
- [ ] `src/core/response_composer.py` 中 `ResponseComposer` 可格式化 context 和 sources
- [ ] `src/core/document_retrieval.py` 不存在
- [ ] `skills/document-retrieval/` 目录不存在
