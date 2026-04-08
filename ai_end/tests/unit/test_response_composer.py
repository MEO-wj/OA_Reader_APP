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


def test_compose_combines_context_and_sources():
    """compose 应将 context 和 sources 组合为完整回答。"""
    from src.core.response_composer import ResponseComposer

    articles = [
        {"title": "文章A", "unit": "教务处", "published_on": "2026-03-20", "summary": "摘要A"},
    ]

    result = ResponseComposer.compose("查询", articles)

    assert "文章A" in result
    assert "来源:" in result


def test_compose_empty_articles():
    """空文章列表应返回空字符串。"""
    from src.core.response_composer import ResponseComposer

    result = ResponseComposer.compose("查询", [])
    assert result == ""
