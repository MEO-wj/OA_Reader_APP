# related_articles 字段兼容性修复设计

## 问题背景

`CompatService._aggregate_events()` 将 ChatClient 的 SSE 事件流聚合为 `/ask` 响应，其中 `related_articles` 存在两个兼容性问题：

1. **Critical**: `grep_article` 的 `tool_result`（格式为 `{status, data, metadata}`）被原样追加到 `related_articles`，不符合前端 `RelatedArticle` 类型，导致渲染崩溃
2. **Important**: `search_articles` 结果缺少 `content_snippet` 字段，前端 `buildSnippet()` 返回空字符串，摘要区域显示空白

## 设计方案

### 1. 按 tool 名称过滤 `tool_result`

**文件**: `ai_end_refactor/src/api/compat_service.py` — `_aggregate_events()` 方法

在处理 `tool_result` 事件时，检查 `event["tool"]` 字段：
- `tool == "search_articles"` → 提取 `results` 列表追加到 `related_articles`（保持现有逻辑）
- 其他工具（`grep_article`、`read_reference` 等）→ **跳过**，不追加

`grep_article` 结果仍然作为 `tool_message` 返回给 LLM 用于生成回答内容，只是不污染 `related_articles` 数组。

### 2. 对 `search_articles` 结果做字段映射

#### 2a. SQL 查询增加 `content_snippet` 字段

**文件**: `ai_end_refactor/src/core/article_retrieval.py`

在向量搜索（`_vector_search`）和关键词搜索（`_search_by_keywords`）的 SQL 中，使用 `LEFT(a.content, 80) as content_snippet` 直接在 SQL 层截取内容前80个字符。不增加 `a.content` 完整字段，避免与 `grep_article` 工具的"获取文章详情"功能重复。

格式化结果中包含 `content_snippet` 和原始 `summary`。

#### 2b. 聚合层新增 `summary_snippet` 字段

**文件**: `ai_end_refactor/src/api/compat_service.py`

在 `_aggregate_events()` 中，从 `search_articles` 提取 results 后，对 `summary` 做截取生成 `summary_snippet`：

```python
def _truncate_text(text: str | None, limit: int = 80) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}…"
```

对每条记录：
- `content_snippet` 直接来自 SQL 结果，无需处理
- `doc["summary_snippet"] = _truncate_text(doc["summary"])`
- **保留原始 `summary` 字段**，不 pop

最终 `related_articles` 中每条记录包含：`content_snippet`、`summary`、`summary_snippet` 三个字段并存。

### 不修改的部分

- **ChatClient**: `tool_result` 事件已包含 `tool` 字段（`client.py:907`），无需修改
- **前端**: 不需要任何修改，`buildSnippet()` 优先级 `content_snippet > summary_snippet > ''` 行为不变
- **`_vector_search` / `_search_by_keywords` 的返回格式**: 只增加 `content_snippet` 字段，不增加完整 `content`，避免与 `grep_article` 功能重叠

## 最终 related_articles 输出结构

```python
{
    "id": int,
    "title": str,
    "unit": str | None,
    "published_on": str | None,
    "content_snippet": str,       # SQL 层 LEFT(content, 80)
    "summary": str,               # 原始完整摘要，保留
    "summary_snippet": str,       # 兼容层截取 summary，限 80 字符
    "ebd_similarity": float | None,
    "keyword_similarity": float | None,
    "rerank_score": float | None,
}
```

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `ai_end_refactor/src/core/article_retrieval.py` | SQL 查询增加 `LEFT(a.content, 80) as content_snippet`，结果格式化包含 `content_snippet` |
| `ai_end_refactor/src/api/compat_service.py` | `_aggregate_events()` 按 tool 名过滤 + 新增 `summary_snippet`（保留 `summary`） |
