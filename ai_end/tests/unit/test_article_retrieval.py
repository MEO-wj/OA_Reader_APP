"""article_retrieval 单元测试"""
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
async def test_search_articles_empty_query():
    """测试空查询字符串抛出异常"""
    with pytest.raises(ValueError, match="查询文本不能为空"):
        await search_articles("", top_k=3, threshold=0.7)


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
