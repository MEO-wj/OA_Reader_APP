"""document_content 单元测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.document_content import (
    ContentFetcher,
    KeywordMatcher,
    LineRangeMatcher,
    RegexMatcher,
    SectionMatcher,
)


class MockPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return AsyncContextManager(self._conn)


class AsyncContextManager:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, exc_type, exc_val, tb):
        return False


@pytest.mark.asyncio
@patch("src.core.document_content.get_pool")
async def test_content_fetcher_cache_hit(mock_get_pool):
    """第二次查询应该使用缓存。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(title="测试文档", content="测试内容")
    mock_get_pool.return_value = MockPool(mock_conn)

    fetcher = ContentFetcher()

    result1 = await fetcher.get(1)
    assert result1 == ("测试文档", "测试内容")

    result2 = await fetcher.get(1)
    assert result2 == ("测试文档", "测试内容")
    assert mock_conn.fetchrow.call_count == 1


@pytest.mark.asyncio
@patch("src.core.document_content.get_pool")
async def test_content_fetcher_not_found(mock_get_pool):
    """文档不存在返回 None。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None
    mock_get_pool.return_value = MockPool(mock_conn)

    fetcher = ContentFetcher()
    result = await fetcher.get(999)

    assert result is None


@pytest.mark.asyncio
async def test_keyword_matcher_basic():
    """测试关键词基本匹配。"""
    content = "第一段内容\n\n第二段包含服务期\n\n第三段"
    matcher = KeywordMatcher()

    results = await matcher.match(content, keyword="服务期")

    assert len(results) == 1
    assert "服务期" in results[0].content


@pytest.mark.asyncio
async def test_keyword_matcher_with_context():
    """测试带上下文的匹配。"""
    content = "前文1\n\n包含关键词的段落\n\n后文1"
    matcher = KeywordMatcher()

    results = await matcher.match(content, keyword="关键词", context_lines=1)

    assert len(results) == 1
    assert len(results[0].context_before) == 1
    assert len(results[0].context_after) == 1


@pytest.mark.asyncio
async def test_keyword_matcher_max_results():
    """测试结果数量限制。"""
    content = "\n\n".join(["包含关键词"] * 10)
    matcher = KeywordMatcher()

    results = await matcher.match(content, keyword="关键词", max_results=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_regex_matcher_basic():
    """测试正则匹配。"""
    content = "第一段 违约责任\n\n第二段 赔偿金额\n\n第三段"
    matcher = RegexMatcher()

    results = await matcher.match(content, pattern=r"违约.*?责任|赔偿.*?金额")

    assert len(results) == 2


@pytest.mark.asyncio
async def test_regex_matcher_no_match():
    """测试无匹配。"""
    content = "完全不相关的内容"
    matcher = RegexMatcher()

    results = await matcher.match(content, pattern=r"不存在")

    assert len(results) == 0


@pytest.mark.asyncio
async def test_section_matcher():
    """测试章节匹配。"""
    content = "第一章 前言\n前言内容\n\n第二章 主体\n主体内容\n\n第三章 结语"
    matcher = SectionMatcher()

    results = await matcher.match(content, section="第二章")

    assert len(results) == 1
    assert "第二章" in results[0].content


@pytest.mark.asyncio
async def test_line_range_matcher():
    """测试行范围匹配。"""
    content = "\n".join([f"第{i}行" for i in range(1, 11)])
    matcher = LineRangeMatcher()

    results = await matcher.match(content, start_line=3, end_line=5)

    assert len(results) == 1
    assert "第3行" in results[0].content
    assert "第5行" in results[0].content


@pytest.mark.asyncio
@patch("src.core.document_content.get_pool")
async def test_content_fetcher_queries_documents_table(mock_get_pool):
    """ContentFetcher 应查询 documents 表而非 policies 表。"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = MagicMock(title="测试文档", content="测试内容")
    mock_get_pool.return_value = MockPool(mock_conn)

    fetcher = ContentFetcher()
    await fetcher.get(1)

    # 验证 SQL 查询使用的是 documents 表
    call_args = mock_conn.fetchrow.call_args
    query = call_args[0][0] if call_args[0] else str(call_args)
    assert "documents" in query.lower(), f"Expected 'documents' in query, got: {query}"