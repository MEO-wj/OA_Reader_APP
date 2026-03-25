"""document_retrieval 单元测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.document_retrieval import (
    generate_embedding,
    grep_documents,
    grep_document,
    search_documents,
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
        """返回 async context manager，而不是协程"""
        return AsyncContextManager(self._conn)


# ========== generate_embedding 测试 ==========


@pytest.mark.asyncio
@patch('src.core.document_retrieval._get_embedding_client')
async def test_generate_embedding_success(mock_get_client):
    """测试成功生成 embedding"""
    # Mock API 响应
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3, 0.4])]

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    result = await generate_embedding("测试文本")

    # 验证返回结果是向量
    assert isinstance(result, list)
    assert all(isinstance(x, float) for x in result)
    mock_client.embeddings.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_embedding_empty_text():
    """测试空文本抛出异常"""
    with pytest.raises(ValueError, match="文本不能为空"):
        await generate_embedding("")


@pytest.mark.asyncio
async def test_generate_embedding_whitespace_only():
    """测试仅包含空格的文本抛出异常"""
    with pytest.raises(ValueError, match="文本不能为空"):
        await generate_embedding("   ")


# ========== search_documents 测试 ==========


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
async def test_search_documents_no_results(mock_generate_embedding, mock_get_pool):
    """测试搜索不存在的文档返回空结果"""
    # Mock embedding 生成
    mock_generate_embedding.return_value = [0.1] * 1536

    # Mock 数据库查询返回空结果
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await search_documents("不存在的文档xyz", top_k=3, threshold=0.7)
    assert "results" in result
    assert len(result["results"]) == 0


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
async def test_search_documents_with_threshold(mock_generate_embedding, mock_get_pool):
    """测试使用高阈值过滤结果"""
    # Mock embedding 生成
    mock_generate_embedding.return_value = [0.1] * 1536

    # Mock 数据库查询返回一些结果
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.98),
        MagicMock(id=2, title="文档B", summary="摘要B", similarity=0.99),
    ]
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await search_documents("订单定向", top_k=5, threshold=0.99)
    assert "results" in result
    assert len(result["results"]) == 2


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
async def test_search_documents_default_params(mock_generate_embedding, mock_get_pool):
    """测试使用默认参数"""
    # Mock embedding 生成
    mock_generate_embedding.return_value = [0.1] * 1536

    # Mock 数据库查询
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await search_documents("测试文档")
    assert "results" in result
    assert isinstance(result["results"], list)


@pytest.mark.asyncio
@patch('src.core.document_retrieval.generate_embedding')
async def test_search_documents_empty_query(mock_generate_embedding):
    """测试空查询字符串抛出异常"""
    with pytest.raises(ValueError, match="查询文本不能为空"):
        await search_documents("", top_k=3, threshold=0.7)


# ========== grep_document 测试 ==========


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_document_not_found(mock_get_pool):
    """测试获取不存在的文档。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_document(document_id=99999, keyword="test")
    assert result["status"] == "not_found"
    assert "error" in result


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_document_by_keyword(mock_get_pool):
    """测试通过关键词搜索文档内容。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(
        title="测试文档",
        content="这是第一段内容，关于服务期的规定。\n\n这是第二段内容，关于违约责任的规定。\n\n这是第三段内容，关于培训费用的规定。",
    )
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_document(document_id=1, keyword="服务期")

    assert result["status"] == "success"
    assert result["data"]["title"] == "测试文档"
    assert len(result["data"]["matches"]) > 0
    assert result["metadata"]["search_mode"] == "keyword"


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_document_no_filters_summary(mock_get_pool):
    """测试无过滤条件时返回摘要模式。"""
    long_content = "这是一段测试内容。" * 100
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(title="长文档测试", content=long_content)
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_document(document_id=1)

    assert result["status"] == "success"
    assert result["metadata"]["search_mode"] == "summary"
    assert len(result["data"]["matches"][0]["content"]) <= 503


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_document_section_not_found(mock_get_pool):
    """测试章节不存在。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(title="测试文档", content="只有第一章内容")
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_document(document_id=1, section="不存在的章节xyz")
    assert result["status"] == "not_found"
    assert "未找到章节" in result["error"]


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_documents_cross_document(mock_get_pool):
    """测试跨文档搜索。"""
    mock_conn = AsyncMock()

    def mock_fetchrow(query, document_id):
        if document_id == 1:
            return MagicMock(title="文档A", content="包含服务期")
        if document_id == 2:
            return MagicMock(title="文档B", content="不包含")
        return None

    mock_conn.fetchrow.side_effect = mock_fetchrow
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_documents([1, 2], keyword="服务期")

    assert result["status"] == "success"
    assert len(result["data"]["results"]) == 1
    assert result["data"]["results"][0]["document_id"] == 1


@pytest.mark.asyncio
@patch('src.core.document_content.get_pool')
async def test_grep_document_keyword_with_delimiters_uses_or_matching(mock_get_pool):
    """测试 keyword 含分隔符时按 OR 匹配。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(
        title="测试文档",
        content="第一段仅有户籍条件。\n\n第二段无关内容。",
    )
    mock_get_pool.return_value = MockPool(mock_conn)

    result = await grep_document(document_id=1, mode="keyword", keyword="农村生源,户籍,农村")

    assert result["status"] == "success"
    assert result["metadata"]["search_mode"] in ("keyword_or", "keyword_or_regex_fallback")
    assert len(result["data"]["matches"]) >= 1


def test_get_embedding_client_singleton(monkeypatch):
    from src.core import api_clients

    api_clients._embedding_client = None

    created = {"count": 0}

    class FakeClient:
        pass

    def fake_openai(*args, **kwargs):
        created["count"] += 1
        return FakeClient()

    # 使用 factory 参数来注入 fake 客户端
    c1 = api_clients.get_embedding_client(factory=fake_openai)
    c2 = api_clients.get_embedding_client(factory=fake_openai)

    assert c1 is c2
    assert created["count"] == 1


@pytest.mark.asyncio
async def test_generate_embedding_uses_queue(monkeypatch):
    from src.core import document_retrieval

    class FakeQueue:
        async def submit(self, lane, func, *args, **kwargs):
            assert lane == "embedding"
            return [0.1, 0.2]

    monkeypatch.setattr(document_retrieval, "get_api_queue", lambda: FakeQueue())

    result = await document_retrieval.generate_embedding("abc")

    assert result == [0.1, 0.2]


# ========== 三层检索策略测试 (Layer 1/2/3) ==========


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval._rerank_documents')
async def test_search_documents_with_keywords_layer2(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试关键词搜索功能（Layer 2）"""
    # Mock embedding 生成
    mock_generate_embedding.return_value = [0.1] * 1024

    # 模拟关键词搜索返回结果
    mock_conn = AsyncMock()

    ebd_call_count = [0]

    async def mock_fetch(query, *args):
        # 检查是否是关键词搜索（通过 SQL 特征）
        if "similarity" in query.lower():
            ebd_call_count[0] += 1
            return []  # EBD 无结果
        else:
            # 关键词搜索
            return [
                MagicMock(id=5, title="培训文档", summary="培训内容", similarity=0.8)
            ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock rerank 返回结果
    mock_rerank.return_value = [
        {
            "id": 5,
            "title": "培训文档",
            "summary": "培训内容",
            "created_at": None,
            "ebd_similarity": None,
            "keyword_similarity": 0.8,
            "rerank_score": 0.9
        }
    ]

    result = await search_documents("培训", keywords="住院医师,培训")

    assert "results" in result


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval._rerank_documents')
async def test_search_documents_merged_results(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试整合层去重逻辑（同一文档在 EBD 和关键词都出现）"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    call_count = [0]

    async def mock_fetch(query, *args):
        call_count[0] += 1
        if call_count[0] == 1:  # EBD 搜索
            return [
                MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.8, created_at=None)
            ]
        else:  # 关键词搜索，返回相同文档
            return [
                MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.7, created_at=None)
            ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock rerank 返回去重后的结果
    mock_rerank.return_value = [
        {
            "id": 1,
            "title": "文档A",
            "summary": "摘要A",
            "created_at": None,
            "ebd_similarity": 0.8,
            "keyword_similarity": 0.7,
            "rerank_score": 0.92
        }
    ]

    result = await search_documents("文档", keywords="关键词")

    # 验证返回结果去重后只有一个文档
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == 1
    assert result["results"][0]["ebd_similarity"] == 0.8
    assert result["results"][0]["keyword_similarity"] == 0.7


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval._rerank_documents')
async def test_search_documents_ebd_only_results(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试只有 EBD 结果的情况（关键词搜索无结果）"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    call_count = [0]

    async def mock_fetch(query, *args):
        call_count[0] += 1
        if call_count[0] == 1:  # EBD 搜索
            return [
                MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.75, created_at=None)
            ]
        else:  # 关键词搜索，无结果
            return []

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock rerank 返回 EBD 结果
    mock_rerank.return_value = [
        {
            "id": 1,
            "title": "文档A",
            "summary": "摘要A",
            "created_at": None,
            "ebd_similarity": 0.75,
            "keyword_similarity": None,
            "rerank_score": 0.88
        }
    ]

    result = await search_documents("文档", keywords="不存在的关键词")

    assert "results" in result
    # 应该返回 EBD 的结果
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == 1
    assert result["results"][0]["ebd_similarity"] == 0.75


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval._rerank_documents')
async def test_search_documents_rerank_scoring(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试 Rerank 排序功能（Layer 3）"""
    from datetime import datetime, timedelta
    from src.core.document_retrieval import search_documents

    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    # 创建不同相似度的数据
    call_count = [0]

    async def mock_fetch(query, *args):
        call_count[0] += 1
        # EBD 搜索返回多个结果，按相似度排序
        return [
            MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.9, created_at=None),
            MagicMock(id=2, title="文档B", summary="摘要B", similarity=0.8, created_at=None),
            MagicMock(id=3, title="文档C", summary="摘要C", similarity=0.7, created_at=None)
        ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock rerank 返回重新排序后的结果（id=2 排到第一，因为与 query 最相关）
    mock_rerank.return_value = [
        {
            "id": 2,
            "title": "文档B",
            "summary": "摘要B",
            "created_at": None,
            "ebd_similarity": 0.8,
            "keyword_similarity": None,
            "rerank_score": 0.98  # 最高分
        },
        {
            "id": 1,
            "title": "文档A",
            "summary": "摘要A",
            "created_at": None,
            "ebd_similarity": 0.9,
            "keyword_similarity": None,
            "rerank_score": 0.85
        },
        {
            "id": 3,
            "title": "文档C",
            "summary": "摘要C",
            "created_at": None,
            "ebd_similarity": 0.7,
            "keyword_similarity": None,
            "rerank_score": 0.75
        }
    ]

    result = await search_documents("文档")

    assert "results" in result
    # 验证 rerank_score 存在且按 rerank_score 降序排列
    assert len(result["results"]) == 3
    assert result["results"][0]["id"] == 2  # rerank 后排第一
    assert result["results"][0]["rerank_score"] == 0.98
    assert result["results"][1]["id"] == 1
    assert result["results"][1]["rerank_score"] == 0.85


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval._rerank_documents')
async def test_search_documents_new_response_structure(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试新的返回结果结构（包含 ebd_similarity, keyword_similarity, rerank_score）"""
    from datetime import datetime, timedelta

    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    new_date = datetime.now() - timedelta(days=100)

    call_count = [0]

    async def mock_fetch(query, *args):
        call_count[0] += 1
        if call_count[0] == 1:  # EBD 搜索
            return [
                MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.8, created_at=new_date)
            ]
        else:  # 关键词搜索
            return [
                MagicMock(id=1, title="文档A", summary="摘要A", similarity=0.7, created_at=new_date)
            ]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock rerank 返回结果
    mock_rerank.return_value = [
        {
            "id": 1,
            "title": "文档A",
            "summary": "摘要A",
            "created_at": new_date,
            "ebd_similarity": 0.8,
            "keyword_similarity": 0.7,
            "rerank_score": 0.92
        }
    ]

    result = await search_documents("文档", keywords="关键词")

    assert "results" in result
    if len(result["results"]) > 0:
        # 验证新字段存在
        first_result = result["results"][0]
        assert "ebd_similarity" in first_result or "similarity" in first_result
        assert "rerank_score" in first_result


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval._rerank_documents')
async def test_search_documents_default_top_k_is_10(mock_rerank, mock_generate_embedding, mock_get_pool):
    """测试默认 top_k 改为 10"""
    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    # 返回超过 10 条结果
    ebd_results = [
        MagicMock(id=i, title=f"文档{i}", summary=f"摘要{i}", similarity=0.8 - i * 0.01, created_at=None)
        for i in range(1, 15)
    ]

    call_count = [0]

    async def mock_fetch(query, *args, **kwargs):
        call_count[0] += 1
        # 第二次调用（关键词）返回空
        if call_count[0] > 1:
            return []
        return ebd_results

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock rerank 返回原始顺序
    candidates = [
        {
            "id": i,
            "title": f"文档{i}",
            "summary": f"摘要{i}",
            "created_at": None,
            "ebd_similarity": 0.8 - i * 0.01,
            "keyword_similarity": None,
        }
        for i in range(1, 15)
    ]
    mock_rerank.return_value = candidates

    result = await search_documents("文档")

    assert "results" in result
    # 默认应该限制返回数量
    assert len(result["results"]) <= 10


# ========== Rerank 相关测试 ==========


@pytest.fixture
def mock_rerank_response():
    """Mock rerank API 响应"""
    return {
        "results": [
            {"index": 2, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.88},
            {"index": 1, "relevance_score": 0.75},
        ]
    }


@pytest.fixture
def mock_rerank_client(mock_rerank_response):
    """Mock rerank 客户端"""
    with patch("src.core.api_clients.get_rerank_client") as mock_get_client:
        mock_client = MagicMock()
        mock_response = MagicMock()

        # 模拟标准响应格式
        mock_response.results = [
            MagicMock(index=2, relevance_score=0.95),
            MagicMock(index=0, relevance_score=0.88),
            MagicMock(index=1, relevance_score=0.75),
        ]
        mock_client.responses.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
@patch('src.core.document_retrieval.get_pool')
@patch('src.core.document_retrieval.generate_embedding')
@patch('src.core.document_retrieval.get_api_queue')
async def test_search_documents_rerank_failure_fallback(mock_get_api_queue, mock_generate_embedding, mock_get_pool):
    """测试 rerank 失败时降级返回原始候选列表"""
    from src.core import document_retrieval

    mock_generate_embedding.return_value = [0.1] * 1024

    mock_conn = AsyncMock()

    # 创建支持字典访问的 Mock 对象
    row1 = MagicMock()
    row1.__getitem__ = lambda self, key: {
        "id": 1,
        "title": "文档A",
        "summary": "摘要A",
        "similarity": 0.8,
        "created_at": None
    }[key]

    row2 = MagicMock()
    row2.__getitem__ = lambda self, key: {
        "id": 2,
        "title": "文档B",
        "summary": "摘要B",
        "similarity": 0.7,
        "created_at": None
    }[key]

    async def mock_fetch(query, *args):
        return [row1, row2]

    mock_conn.fetch = mock_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    # Mock API 队列提交时抛出异常（模拟 API 失败）
    async def fake_submit(lane, func, *args, **kwargs):
        if lane == "rerank":
            raise RuntimeError("Rerank API 调用失败")
        # 其他 lane 正常执行
        return await func(*args, **kwargs)

    mock_get_api_queue.return_value.submit = fake_submit

    result = await document_retrieval.search_documents("测试查询")

    # 验证降级返回 EBD 结果（_rerank_documents 内部捕获异常）
    assert "results" in result
    assert len(result["results"]) == 2
    # 应该返回原始 EBD 结果（没有 rerank_score，因为降级了）
    assert result["results"][0]["id"] == 1
    assert result["results"][0]["ebd_similarity"] == 0.8
    assert result["results"][0].get("rerank_score") is None


@pytest.mark.asyncio
async def test_rerank_documents_sync_empty_candidates():
    """测试空候选列表直接返回"""
    from src.core.document_retrieval import _rerank_documents_sync

    result = _rerank_documents_sync("查询", [])
    assert result == []


@pytest.mark.asyncio
async def test_rerank_documents_sync_with_client_error(monkeypatch):
    """测试 rerank 客户端错误时抛出 RuntimeError"""
    from src.core.document_retrieval import _rerank_documents_sync

    def fake_get_rerank_client():
        raise RuntimeError("Rerank API 调用失败: 无法连接 rerank 服务")

    monkeypatch.setattr("src.core.document_retrieval._get_rerank_client", fake_get_rerank_client)

    with pytest.raises(RuntimeError, match="Rerank API 调用失败"):
        _rerank_documents_sync("查询", [{"id": 1, "title": "测试"}])