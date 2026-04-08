# related_articles 字段兼容性修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 `_aggregate_events()` 中 related_articles 的两个兼容性问题：按 tool 名过滤 + 补充 content_snippet/summary_snippet 字段

**Architecture:** 两处独立修改——article_retrieval.py 的 SQL 查询增加 content_snippet 字段；compat_service.py 的 _aggregate_events() 按 tool 名过滤并生成 summary_snippet。两层修改互不依赖。

**Tech Stack:** Python 3.11+, asyncpg (PostgreSQL), pytest

---

### Task 1: _aggregate_events 按 tool 名称过滤 tool_result

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py:133-194`
- Test: `ai_end_refactor/tests/unit/test_compat_service.py`

**Step 1: 写失败测试 — grep_article 的 tool_result 不应追加到 related_articles**

在 `test_compat_service.py` 的 `TestAggregateEvents` 类中新增测试：

```python
def test_aggregate_events_skips_non_search_articles_tool_results(self):
    """grep_article 等非 search_articles 的 tool_result 不应追加到 related_articles。"""
    from src.api.compat_service import CompatService

    events = [
        {"type": "tool_result", "tool": "grep_article", "result": '{"status": "success", "data": {}}'},
        {"type": "tool_result", "tool": "read_reference", "result": '{"text": "ref"}'},
        {"type": "tool_result", "tool": "search_articles", "result": '[{"title": "有效文章"}]'},
    ]
    result = CompatService._aggregate_events(events)

    assert len(result["related_articles"]) == 1
    assert result["related_articles"][0]["title"] == "有效文章"
```

**Step 2: 运行测试验证失败**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_aggregate_events_skips_non_search_articles_tool_results -v`
Expected: FAIL — grep_article 的结果也被追加，related_articles 长度为 3

**Step 3: 实现最小改动**

在 `compat_service.py` 的 `_aggregate_events()` 方法中，`elif event_type == "tool_result":` 分支内，解析 parsed 之后、追加到 related_articles 之前，增加 tool 名过滤：

```python
# 只提取 search_articles 的结果
tool_name = event.get("tool", "")
if tool_name != "search_articles":
    continue
```

在 `elif event_type == "tool_result":` 分支的开头（raw_result 解析之前）插入。

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestAggregateEvents -v`
Expected: 全部 PASS

**Step 5: 运行全量 compat_service 测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: 全部 PASS

---

### Task 2: _truncate_text 辅助函数 + summary_snippet 生成

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py`（新增 `_truncate_text` 静态函数）
- Test: `ai_end_refactor/tests/unit/test_compat_service.py`

**Step 1: 写失败测试 — _truncate_text 函数**

在 `test_compat_service.py` 的 `TestAggregateEvents` 类中新增测试：

```python
def test_truncate_text_short(self):
    """短文本不截断，直接返回。"""
    from src.api.compat_service import CompatService
    assert CompatService._truncate_text("短文本") == "短文本"

def test_truncate_text_none(self):
    """None 返回空字符串。"""
    from src.api.compat_service import CompatService
    assert CompatService._truncate_text(None) == ""

def test_truncate_text_empty(self):
    """空字符串返回空字符串。"""
    from src.api.compat_service import CompatService
    assert CompatService._truncate_text("") == ""

def test_truncate_text_long(self):
    """超长文本截取到 limit 并加省略号。"""
    from src.api.compat_service import CompatService
    text = "这是一段非常长的文本用来测试截断功能是否正常工作"
    result = CompatService._truncate_text(text, limit=10)
    assert len(result) <= 11  # 10字符 + 省略号
    assert result.endswith("…")

def test_truncate_text_collapses_whitespace(self):
    """多余空白应被压缩为单空格。"""
    from src.api.compat_service import CompatService
    text = "这是  多余   空白"
    result = CompatService._truncate_text(text)
    assert "  " not in result
    assert result == "这是 多余 空白"
```

**Step 2: 运行测试验证失败**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_truncate_text_short -v`
Expected: FAIL — `_truncate_text` 不存在

**Step 3: 实现 _truncate_text**

在 `compat_service.py` 的 `CompatService` 类中，`_aggregate_events` 方法之前添加静态方法：

```python
@staticmethod
def _truncate_text(text: str | None, limit: int = 80) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}…"
```

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestAggregateEvents -v`
Expected: 全部 PASS

---

### Task 3: _aggregate_events 中生成 summary_snippet 字段

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py:133-194`
- Test: `ai_end_refactor/tests/unit/test_compat_service.py`

**Step 1: 写失败测试 — related_articles 应包含 summary_snippet 且保留 summary**

在 `test_compat_service.py` 的 `TestAggregateEvents` 类中新增测试：

```python
def test_aggregate_events_adds_summary_snippet_and_keeps_summary(self):
    """search_articles 的 results 应新增 summary_snippet，且保留原始 summary。"""
    from src.api.compat_service import CompatService

    events = [
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": json.dumps({"results": [
                {"id": 1, "title": "文章A", "summary": "这是一段非常长的摘要内容用来测试截断功能是否正常工作不截断的话会太长"},
                {"id": 2, "title": "文章B", "summary": "短摘要"},
            ]}),
        },
    ]
    result = CompatService._aggregate_events(events)

    articles = result["related_articles"]
    assert len(articles) == 2

    # 文章A: 长 summary → 应有截断的 summary_snippet
    assert articles[0]["summary"] == "这是一段非常长的摘要内容用来测试截断功能是否正常工作不截断的话会太长"
    assert "summary_snippet" in articles[0]
    assert len(articles[0]["summary_snippet"]) <= 81
    assert articles[0]["summary_snippet"].endswith("…")

    # 文章B: 短 summary → summary_snippet == summary
    assert articles[1]["summary_snippet"] == "短摘要"
    assert articles[1]["summary"] == "短摘要"

def test_aggregate_events_handles_missing_summary(self):
    """缺少 summary 字段时 summary_snippet 应为空字符串。"""
    from src.api.compat_service import CompatService

    events = [
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": json.dumps({"results": [
                {"id": 1, "title": "无摘要文章"},
            ]}),
        },
    ]
    result = CompatService._aggregate_events(events)

    assert result["related_articles"][0]["summary_snippet"] == ""
```

注意：需要在测试文件顶部已有 `import json`，检查是否已存在（已存在于 compat_service.py 但测试文件需要确认）。若测试文件没有 `import json`，需添加。

**Step 2: 运行测试验证失败**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_aggregate_events_adds_summary_snippet_and_keeps_summary -v`
Expected: FAIL — `summary_snippet` 字段不存在

**Step 3: 实现 summary_snippet 生成**

在 `_aggregate_events()` 方法中，当 tool == "search_articles" 且解析出 results 列表后，对每条记录生成 summary_snippet：

在现有的 `related_articles.extend(parsed)` / `related_articles.extend(results)` 之前，对 results 中的每条 doc 调用 `_truncate_text`：

```python
# 为每条记录生成 summary_snippet
for doc in results:
    doc["summary_snippet"] = CompatService._truncate_text(doc.get("summary"))
```

注意：results 是列表，如果是 dict 格式的 parsed（非 results 列表），也需处理。

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestAggregateEvents -v`
Expected: 全部 PASS

**Step 5: 运行全量 compat_service 测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: 全部 PASS

---

### Task 4: SQL 查询增加 content_snippet 字段

**Files:**
- Modify: `ai_end_refactor/src/core/article_retrieval.py`
- Test: `ai_end_refactor/tests/unit/test_article_retrieval.py`

**Step 1: 写失败测试 — formatted_results 应包含 content_snippet**

在 `test_article_retrieval.py` 中新增测试（使用现有 mock 模式）：

```python
@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_returns_content_snippet(mock_rerank, mock_generate_embedding, mock_get_pool):
    """search_articles 结果应包含 content_snippet 字段。"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": 1,
        "title": "文章A",
        "unit": "教务处",
        "published_on": "2026-03-20",
        "summary": "摘要内容",
        "similarity": 0.9,
        "content_snippet": "这是文章正文前80个字符的截取内容用于展示在搜索结果列表中",
    }[key]

    async def mock_fetch(query, *args):
        return [row]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 1,
            "title": "文章A",
            "unit": "教务处",
            "published_on": "2026-03-20",
            "summary": "摘要内容",
            "ebd_similarity": 0.9,
            "keyword_similarity": None,
            "rerank_score": 0.85,
            "content_snippet": "这是文章正文前80个字符的截取内容用于展示在搜索结果列表中",
        }
    ]

    result = await search_articles("测试查询")

    assert "results" in result
    assert len(result["results"]) == 1
    assert "content_snippet" in result["results"][0]
    assert result["results"][0]["content_snippet"] == "这是文章正文前80个字符的截取内容用于展示在搜索结果列表中"
```

**Step 2: 运行测试验证失败**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_article_retrieval.py::test_search_articles_returns_content_snippet -v`
Expected: FAIL — `content_snippet` 字段不在结果中

**Step 3: 修改 SQL 和格式化逻辑**

修改 `article_retrieval.py` 中两处：

**(a) _vector_search SQL（约第 198 行）**

将：
```sql
SELECT v.id, a.title, a.unit, a.published_on, a.summary,
       1 - (v.embedding <=> $1::vector) as similarity
```

改为：
```sql
SELECT v.id, a.title, a.unit, a.published_on, a.summary,
       LEFT(a.content, 80) as content_snippet,
       1 - (v.embedding <=> $1::vector) as similarity
```

**(b) _search_by_keywords SQL（约第 328 行）**

将：
```sql
SELECT id, title, unit, published_on, summary,
       GREATEST(
           similarity(title, $2),
           similarity(content, $2)
       ) as similarity
```

改为：
```sql
SELECT id, title, unit, published_on, summary,
       LEFT(content, 80) as content_snippet,
       GREATEST(
           similarity(title, $2),
           similarity(content, $2)
       ) as similarity
```

同时在 `_search_by_keywords` 的 dict 构建中添加 `"content_snippet": row["content_snippet"]`。

**(c) formatted_results 构建中添加 content_snippet**

在 `search_articles()` 函数的 `formatted_results.append({...})` 中添加：
```python
"content_snippet": doc.get("content_snippet"),
```

同时检查 merge 逻辑中 `_merge_results` 是否需要传递 `content_snippet`，确保从 `_vector_search` 返回的 row 包含该字段后，中间处理层不会丢弃。

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_article_retrieval.py::test_search_articles_returns_content_snippet -v`
Expected: PASS

**Step 5: 运行全量 article_retrieval 测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_article_retrieval.py -v`
Expected: 全部 PASS

---

### Task 5: 全量测试与集成验证

**Step 1: 运行 ai_end_refactor 全量单元测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/ -v`
Expected: 全部 PASS

**Step 2: 运行集成测试（如环境可用）**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -v`
Expected: 全部 PASS（若无测试环境可跳过）
