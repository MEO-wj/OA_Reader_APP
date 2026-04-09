"""article_retrieval 单元测试"""
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.article_retrieval import (
    generate_embedding,
    grep_articles,
    grep_article,
    search_articles,
)


# ========== Mock 辅助类 ==========


class AsyncContextManager:
    """Mock async context manager"""
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPool:
    """Mock async pool with acquire() returning async context manager"""
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return AsyncContextManager(self._conn)


# ========== 基本结构测试 ==========


def test_article_retriever_exists():
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
    assert "vectors" in retriever.table_name


def test_search_articles_function_exists():
    """search_articles 顶层函数应存在。"""
    assert callable(search_articles)


def test_grep_article_function_exists():
    """grep_article 顶层函数应存在。"""
    assert callable(grep_article)


def test_grep_articles_function_exists():
    """grep_articles 顶层函数应存在。"""
    assert callable(grep_articles)


# ========== generate_embedding 测试 ==========


@pytest.mark.asyncio
@patch('src.core.base_retrieval.get_embedding_client')
async def test_generate_embedding_success(mock_get_client):
    """测试成功生成 embedding"""
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3, 0.4])]

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await generate_embedding("测试文本")

    assert isinstance(result, list)
    assert all(isinstance(x, float) for x in result)
    mock_client.embeddings.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_embedding_empty_text():
    """测试空文本抛出异常"""
    with pytest.raises(ValueError, match="文本不能为空"):
        await generate_embedding("")


# ========== search_articles 测试 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
async def test_search_articles_no_results(mock_generate_embedding, mock_get_pool):
    """测试搜索不存在的文章返回空结果"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await search_articles("不存在的文章xyz", top_k=3, threshold=0.7)
    assert "results" in result
    assert len(result["results"]) == 0


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
async def test_search_articles_with_threshold(mock_generate_embedding, mock_get_pool):
    """测试使用高阈值过滤结果"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-03-20", summary="摘要A", similarity=0.98),
        MagicMock(id=2, title="文章B", unit="学工处", published_on="2026-03-15", summary="摘要B", similarity=0.99),
    ]
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await search_articles("期末考试", top_k=5, threshold=0.99)
    assert "results" in result
    assert len(result["results"]) == 2


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
async def test_search_articles_empty_query(mock_get_pool):
    """空查询不再抛异常，走时间排序分支返回最新文章。"""
    mock_conn = AsyncMock()
    captured_sql = []

    rows_data = [
        {"id": 3, "title": "文章C", "unit": "学工处", "published_on": "2026-04-09", "summary": "最新", "content_snippet": "内容C"},
        {"id": 2, "title": "文章B", "unit": "教务处", "published_on": "2026-04-08", "summary": "中等", "content_snippet": "内容B"},
        {"id": 1, "title": "文章A", "unit": "人事处", "published_on": "2026-04-07", "summary": "最早", "content_snippet": "内容A"},
    ]

    def make_row(data):
        row = MagicMock()
        row.__getitem__ = lambda self, key, d=data: d[key]
        return row

    async def capture_fetch(sql, *args):
        captured_sql.append(sql)
        return [make_row(d) for d in rows_data]

    mock_conn.fetch = capture_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await search_articles(query="", top_k=3)

    assert "results" in result
    assert len(result["results"]) == 3
    assert result["results"][0]["id"] == 3  # newest first


# ========== grep_article 测试 ==========


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_article_not_found(mock_get_pool):
    """测试获取不存在的文章。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_article(article_id=99999, keyword="test")
    assert result["status"] == "not_found"
    assert "error" in result


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_article_by_keyword(mock_get_pool):
    """测试通过关键词搜索文章内容。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(
        title="测试文章",
        content="这是第一段内容，关于服务期的规定。\n\n这是第二段内容，关于违约责任的规定。\n\n这是第三段内容，关于培训费用的规定。",
    )
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_article(article_id=1, keyword="服务期")

    assert result["status"] == "success"
    assert result["data"]["title"] == "测试文章"
    assert len(result["data"]["matches"]) > 0
    assert result["metadata"]["search_mode"] == "keyword"


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_article_no_filters_summary(mock_get_pool):
    """测试无过滤条件时返回摘要模式。"""
    long_content = "这是一段测试内容。" * 100
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(title="长文章测试", content=long_content)
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_article(article_id=1)

    assert result["status"] == "success"
    assert result["metadata"]["search_mode"] == "summary"
    assert len(result["data"]["matches"][0]["content"]) <= 503


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_articles_cross_article(mock_get_pool):
    """测试跨文章搜索。"""
    mock_conn = AsyncMock()

    def mock_fetchrow(query, article_id):
        if article_id == 1:
            return MagicMock(title="文章A", content="包含服务期")
        if article_id == 2:
            return MagicMock(title="文章B", content="不包含")
        return None

    mock_conn.fetchrow.side_effect = mock_fetchrow
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_articles([1, 2], keyword="服务期")

    assert result["status"] == "success"
    assert len(result["data"]["results"]) == 1
    assert result["data"]["results"][0]["article_id"] == 1


# ========== 三层检索策略测试 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_with_keywords_layer2(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试关键词搜索功能（Layer 2）"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    async def mock_fetch(query, *args):
        if "similarity" in query.lower():
            return []
        else:
            return [
                MagicMock(id=5, title="培训通知", unit="教务处", published_on="2026-03-20", summary="培训内容")
            ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 5,
            "title": "培训通知",
            "unit": "教务处",
            "published_on": "2026-03-20",
            "summary": "培训内容",
            "ebd_similarity": None,
            "keyword_similarity": 0.8,
            "rerank_score": 0.9
        }
    ]

    result = await search_articles("培训", keywords="住院医师,培训")

    assert "results" in result


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_merged_results(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试整合层去重逻辑（同一文章在 EBD 和关键词都出现）"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    call_count = [0]

    async def mock_fetch(query, *args):
        call_count[0] += 1
        if call_count[0] == 1:
            return [
                MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-03-20", summary="摘要A", similarity=0.8)
            ]
        else:
            return [
                MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-03-20", summary="摘要A", similarity=0.7)
            ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 1,
            "title": "文章A",
            "unit": "教务处",
            "published_on": "2026-03-20",
            "summary": "摘要A",
            "ebd_similarity": 0.8,
            "keyword_similarity": 0.7,
            "rerank_score": 0.92
        }
    ]

    result = await search_articles("文章", keywords="关键词")

    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == 1
    assert result["results"][0]["ebd_similarity"] == 0.8
    assert result["results"][0]["keyword_similarity"] == 0.7


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_rerank_scoring(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试 Rerank 排序功能（Layer 3）"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    async def mock_fetch(query, *args):
        return [
            MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-03-20", summary="摘要A", similarity=0.9),
            MagicMock(id=2, title="文章B", unit="学工处", published_on="2026-03-15", summary="摘要B", similarity=0.8),
            MagicMock(id=3, title="文章C", unit="人事处", published_on="2026-03-10", summary="摘要C", similarity=0.7)
        ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 2, "title": "文章B", "unit": "学工处", "published_on": "2026-03-15",
            "summary": "摘要B", "ebd_similarity": 0.8, "keyword_similarity": None, "rerank_score": 0.98
        },
        {
            "id": 1, "title": "文章A", "unit": "教务处", "published_on": "2026-03-20",
            "summary": "摘要A", "ebd_similarity": 0.9, "keyword_similarity": None, "rerank_score": 0.85
        },
        {
            "id": 3, "title": "文章C", "unit": "人事处", "published_on": "2026-03-10",
            "summary": "摘要C", "ebd_similarity": 0.7, "keyword_similarity": None, "rerank_score": 0.75
        }
    ]

    result = await search_articles("文章")

    assert "results" in result
    assert len(result["results"]) == 3
    assert result["results"][0]["id"] == 2
    assert result["results"][0]["rerank_score"] == 0.98


# ========== Rerank 相关测试 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval.get_api_queue')
async def test_search_articles_rerank_failure_fallback(mock_get_api_queue, mock_generate_embedding, mock_get_pool):
    """测试 rerank 失败时降级返回原始候选列表"""
    from src.core import article_retrieval

    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    row1 = MagicMock()
    row1.__getitem__ = lambda self, key: {
        "id": 1, "title": "文章A", "unit": "教务处", "published_on": "2026-03-20",
        "summary": "摘要A", "similarity": 0.8
    }[key]

    row2 = MagicMock()
    row2.__getitem__ = lambda self, key: {
        "id": 2, "title": "文章B", "unit": "学工处", "published_on": "2026-03-15",
        "summary": "摘要B", "similarity": 0.7
    }[key]

    async def mock_fetch(query, *args):
        return [row1, row2]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    async def fake_submit(lane, func, *args, **kwargs):
        if lane == "rerank":
            raise RuntimeError("Rerank API 调用失败")
        return await func(*args, **kwargs)

    mock_get_api_queue.return_value.submit = fake_submit

    result = await article_retrieval.search_articles("测试查询")

    assert "results" in result
    assert len(result["results"]) == 2


@pytest.mark.asyncio
async def test_rerank_documents_sync_empty_candidates():
    """测试空候选列表直接返回"""
    from src.core.article_retrieval import _rerank_documents_sync

    result = _rerank_documents_sync("查询", [])
    assert result == []


@pytest.mark.asyncio
async def test_rerank_documents_sync_with_client_error(monkeypatch):
    """测试 rerank 客户端错误时抛出 RuntimeError"""
    from src.core.article_retrieval import _rerank_documents_sync

    def fake_get_rerank_client():
        raise RuntimeError("Rerank API 调用失败: 无法连接 rerank 服务")

    monkeypatch.setattr("src.core.article_retrieval._get_rerank_client", fake_get_rerank_client)

    with pytest.raises(RuntimeError, match="Rerank API 调用失败"):
        _rerank_documents_sync("查询", [{"id": 1, "title": "测试"}])


@pytest.mark.asyncio
async def test_generate_embedding_uses_queue(monkeypatch):
    from src.core import base_retrieval

    class FakeQueue:
        async def submit(self, lane, func, *args, **kwargs):
            assert lane == "embedding"
            return [0.1, 0.2]

    monkeypatch.setattr(base_retrieval, "get_api_queue", lambda: FakeQueue())

    result = await base_retrieval.generate_embedding("abc")

    assert result == [0.1, 0.2]


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


# ========== article_id 正确性测试 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_vector_search_uses_article_id_not_vector_id(mock_rerank, mock_generate_embedding, mock_get_pool):
    """_vector_search 的 SQL 应 SELECT a.id（articles 主键）而非 v.id（vectors 主键）。

    vectors 表有自己的 BIGSERIAL 主键 id，通过 article_id 外键关联 articles。
    前端需要 articles.id 来调用 /api/articles/:id 获取详情。
    """
    from src.core.article_retrieval import ArticleRetriever

    mock_generate_embedding.return_value = [0.1] * 1024

    # 模拟数据库返回：row["id"] 应该是 article id (500)，而非 vector id (1)
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": 500,
        "title": "测试文章",
        "unit": "测试单位",
        "published_on": "2026-03-20",
        "summary": "测试摘要",
        "content_snippet": "正文片段",
        "similarity": 0.9,
    }[key]

    mock_conn = AsyncMock()
    captured_sql = []

    async def capture_fetch(sql, *args):
        captured_sql.append(sql)
        return [row]

    mock_conn.fetch = capture_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 500,
            "title": "测试文章",
            "unit": "测试单位",
            "published_on": "2026-03-20",
            "summary": "测试摘要",
            "content_snippet": "正文片段",
            "ebd_similarity": 0.9,
            "keyword_similarity": None,
            "rerank_score": 0.85,
        }
    ]

    retriever = ArticleRetriever()
    await retriever.search_articles("测试查询", top_k=1)

    # 验证 SQL 的 SELECT 子句使用 a.id 而非 v.id 作为 id 列
    assert len(captured_sql) >= 1
    vector_sql = captured_sql[0]
    # 提取 SELECT 行来精确检查列名
    select_line = ""
    for line in vector_sql.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("SELECT"):
            select_line = stripped
            break
    assert select_line, f"未找到 SELECT 子句，SQL: {vector_sql[:200]}"
    # SELECT 子句中不应包含 "v.id"（vectors 表主键）
    assert "v.id" not in select_line, (
        f"SELECT 子句使用了 v.id (vectors 主键) 而非 a.id (articles 主键)。"
        f" SELECT: {select_line}"
    )
    # SELECT 子句中应包含 "a.id"（articles 表主键）
    assert "a.id" in select_line, (
        f"SELECT 子句应包含 a.id (articles 主键)。"
        f" SELECT: {select_line}"
    )


# ========== content_snippet 字段测试 ==========


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


# ========== Task 4: 检索层日期过滤（有 query 分支）==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_adds_date_range_filter_to_sql(mock_rerank, mock_generate_embedding, mock_get_pool):
    """当 query + start_date + end_date 都传入时，SQL 应包含 published_on 过滤条件。"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()
    captured_sql = []

    async def capture_fetch(sql, *args):
        captured_sql.append(sql)
        return [
            MagicMock(id=1, title="奖学金通知", unit="学工处", published_on="2026-04-05", summary="摘要", similarity=0.9)
        ]

    mock_conn.fetch = capture_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 1, "title": "奖学金通知", "unit": "学工处", "published_on": "2026-04-05",
            "summary": "摘要", "ebd_similarity": 0.9, "keyword_similarity": None, "rerank_score": 0.95,
        }
    ]

    await search_articles("奖学金", start_date="2026-04-01", end_date="2026-04-09")

    assert len(captured_sql) >= 1
    vector_sql = captured_sql[0]
    assert "published_on" in vector_sql, f"SQL 中应包含 published_on 过滤条件。SQL: {vector_sql[:300]}"


# ========== Task 6: 时效性加权排序 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_recency_weighting_newer_higher_score(mock_rerank, mock_generate_embedding, mock_get_pool):
    """相同 similarity 时，更新的文章应有更高的 final_score。

    公式：final_score = similarity + 0.1 * exp(-days_old / 30)
    """
    mock_generate_embedding.return_value = [0.1] * 1024

    # 两个结果 similarity 相同，但日期不同
    row_old = MagicMock()
    row_old.__getitem__ = lambda self, key: {
        "id": 1, "title": "旧文章", "unit": "教务处",
        "published_on": "2026-03-10", "summary": "旧摘要",
        "content_snippet": "旧内容", "similarity": 0.8,
    }[key]

    row_new = MagicMock()
    row_new.__getitem__ = lambda self, key: {
        "id": 2, "title": "新文章", "unit": "教务处",
        "published_on": "2026-04-08", "summary": "新摘要",
        "content_snippet": "新内容", "similarity": 0.8,
    }[key]

    mock_conn = AsyncMock()

    async def mock_fetch(query, *args):
        return [row_old, row_new]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # rerank 保持原始顺序（不做实际 rerank）
    mock_rerank.side_effect = lambda query, candidates, top_k: candidates

    result = await search_articles("测试")

    assert "results" in result
    # 新文章的 final_score 应高于旧文章
    old_item = next(r for r in result["results"] if r["id"] == 1)
    new_item = next(r for r in result["results"] if r["id"] == 2)

    assert "final_score" in new_item, "结果应包含 final_score 字段"
    assert "final_score" in old_item, "结果应包含 final_score 字段"
    assert new_item["final_score"] > old_item["final_score"], (
        f"新文章 final_score({new_item['final_score']}) 应高于旧文章({old_item['final_score']})"
    )


# ========== Task 7: 日期边界与容错行为 ==========


def test_normalize_date_range_swapped():
    """start_date > end_date 时自动交换。"""
    from src.core.article_retrieval import _normalize_date_range
    sd, ed = _normalize_date_range("2026-04-09", "2026-04-01")
    assert sd is not None and ed is not None
    assert sd <= ed, f"交换后 start({sd}) 应 <= end({ed})"


def test_normalize_date_range_invalid_ignored():
    """无效日期格式被忽略，对应边界为 None。"""
    from src.core.article_retrieval import _normalize_date_range
    sd, ed = _normalize_date_range("not-a-date", "2026-04-09")
    assert sd is None, f"无效 start_date 应被忽略，但得到 {sd}"
    assert ed is not None


def test_normalize_date_range_single_start_defaults_end_to_today():
    """仅传 start_date 时，end_date 默认为今天。"""
    from src.core.article_retrieval import _normalize_date_range
    from datetime import date
    sd, ed = _normalize_date_range("2026-04-01", None)
    assert sd == date(2026, 4, 1)
    assert ed is not None  # 默认今天


def test_normalize_date_range_single_end_no_lower_bound():
    """仅传 end_date 时，不设置下界（start=None）。"""
    from src.core.article_retrieval import _normalize_date_range
    sd, ed = _normalize_date_range(None, "2026-04-09")
    assert sd is None, f"仅传 end_date 时 start 应为 None，但得到 {sd}"
    assert ed is not None


def test_normalize_date_range_both_none():
    """两个都为 None 时不做任何过滤。"""
    from src.core.article_retrieval import _normalize_date_range
    sd, ed = _normalize_date_range(None, None)
    assert sd is None
    assert ed is None


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_with_swapped_dates_still_works(mock_rerank, mock_generate_embedding, mock_get_pool):
    """start_date > end_date 自动交换后仍然正常搜索。"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    async def mock_fetch(sql, *args):
        return [
            MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-04-05", summary="摘要A", similarity=0.9)
        ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 1, "title": "文章A", "unit": "教务处", "published_on": "2026-04-05",
            "summary": "摘要A", "ebd_similarity": 0.9, "keyword_similarity": None, "rerank_score": 0.9,
        }
    ]

    result = await search_articles("测试", start_date="2026-04-09", end_date="2026-04-01")
    assert "results" in result
    assert len(result["results"]) == 1


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_with_invalid_date_degrades_gracefully(mock_rerank, mock_generate_embedding, mock_get_pool):
    """无效日期格式被忽略，搜索降级为无日期过滤。"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()
    captured_sql = []

    async def capture_fetch(sql, *args):
        captured_sql.append(sql)
        return [
            MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-04-05", summary="摘要A", similarity=0.9)
        ]

    mock_conn.fetch = capture_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = [
        {
            "id": 1, "title": "文章A", "unit": "教务处", "published_on": "2026-04-05",
            "summary": "摘要A", "ebd_similarity": 0.9, "keyword_similarity": None, "rerank_score": 0.9,
        }
    ]

    result = await search_articles("测试", start_date="invalid-date", end_date="2026-04-09")
    assert "results" in result
    # 无效 start_date 被忽略，end_date 仍有效 -> SQL 仍应有 published_on 过滤
    assert len(captured_sql) >= 1


# ========== Layer 2 关键词搜索日期过滤测试 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
@patch('src.core.article_retrieval.generate_embedding')
@patch('src.core.article_retrieval._rerank_documents')
async def test_search_articles_keyword_layer_respects_date_range(mock_rerank, mock_generate_embedding, mock_get_pool):
    """关键词搜索（Layer 2）的 SQL 应包含日期过滤条件。"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()
    captured_sqls = []

    async def capture_fetch(sql, *args):
        captured_sqls.append(sql)
        return []

    mock_conn.fetch = capture_fetch
    mock_conn.execute = AsyncMock()
    mock_get_pool.return_value = MockPool(mock_conn)

    mock_rerank.return_value = []

    await search_articles("培训", keywords="培训", start_date="2026-04-01", end_date="2026-04-09")

    # 第二条 SQL 应为关键词搜索（包含 pg_trgm 的 similarity 函数）
    keyword_sqls = [s for s in captured_sqls if "similarity" in s.lower() and "articles" in s.lower()]
    assert len(keyword_sqls) >= 1, (
        f"应有关键词搜索 SQL，但捕获的 SQL 为: {[s[:100] for s in captured_sqls]}"
    )
    kw_sql = keyword_sqls[0]
    assert "published_on" in kw_sql, (
        f"关键词搜索 SQL 应包含 published_on 日期过滤条件。SQL: {kw_sql[:300]}"
    )


# ========== Fix 2: _today() 传参化 ==========


def test_normalize_date_range_accepts_today_param():
    """_normalize_date_range 应接受 today 参数，避免内部调用 Config.load()。"""
    from src.core.article_retrieval import _normalize_date_range
    from datetime import date
    fixed_today = date(2026, 4, 1)
    sd, ed = _normalize_date_range("2026-03-01", None, today=fixed_today)
    assert sd == date(2026, 3, 1)
    assert ed == fixed_today, f"仅传 start_date 时 end 应等于传入的 today({fixed_today})"


def test_normalize_date_range_without_today_uses_default():
    """_normalize_date_range 不传 today 时仍向后兼容。"""
    from src.core.article_retrieval import _normalize_date_range
    sd, ed = _normalize_date_range("2026-04-01", "2026-04-09")
    assert sd is not None
    assert ed is not None


def test_apply_recency_weighting_accepts_today_param():
    """_apply_recency_weighting 应接受 today 参数，避免内部调用 Config.load()。"""
    from src.core.article_retrieval import _apply_recency_weighting
    from datetime import date
    fixed_today = date(2026, 4, 15)
    candidates = [
        {"published_on": "2026-04-10", "rerank_score": 0.8},
        {"published_on": "2026-04-14", "rerank_score": 0.8},
    ]
    result = _apply_recency_weighting(candidates, today=fixed_today)
    # 排序后 4/14（更新）排在前面
    assert result[0]["final_score"] > result[1]["final_score"]


# ========== Fix 3: 空 query 无日期时防御性日志 ==========


@pytest.mark.asyncio
@patch('src.core.article_retrieval.get_pool')
async def test_search_by_time_logs_warning_when_no_date_filters(mock_get_pool, caplog):
    """空 query 且无日期过滤时，应输出 warning 日志提示可能的性能问题。"""
    from src.core.article_retrieval import ArticleRetriever

    mock_conn = AsyncMock()
    async def mock_fetch(sql, *args):
        return [
            MagicMock(id=1, title="文章A", unit="教务处", published_on="2026-04-09",
                       summary="摘要A", content_snippet="内容A"),
        ]
    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    retriever = ArticleRetriever()
    with caplog.at_level(logging.WARNING, logger="src.core.article_retrieval"):
        result = await retriever._search_by_time(top_k=3)

    assert "results" in result
    # 无日期过滤时应有 warning 日志
    assert any(
        "无日期过滤" in record.message
        for record in caplog.records
    ), f"应输出包含'无日期过滤'的 warning 日志，实际日志: {[r.message for r in caplog.records]}"
