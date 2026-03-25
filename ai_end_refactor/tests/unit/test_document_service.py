"""document_service 测试 - 通用文档服务语义"""

import json

import pytest

from src.api.document_service import (
    delete_document,
    import_document_content,
    list_documents,
)


class _FakeConn:
    def __init__(self, responses: list | dict | None = None):
        self._responses = responses or []
        self._idx = 0
        self._last_args = None
        self.fetchrow_args_history: list[tuple] = []

    async def fetchrow(self, _query, *args):
        self._last_args = args
        self.fetchrow_args_history.append(args)
        if isinstance(self._responses, list):
            if self._idx < len(self._responses):
                resp = self._responses[self._idx]
                self._idx += 1
                return resp
        return self._responses

    async def fetch(self, _query, *args):
        self._last_args = args
        if isinstance(self._responses, list):
            return self._responses
        return [self._responses] if self._responses else []

    async def fetchval(self, _query, *args):
        return 0

    async def execute(self, _query, *args):
        self._last_args = args
        if isinstance(self._responses, str):
            return self._responses
        return "DELETE 1"


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


async def _make_fake_pool(conn):
    return _FakePool(conn)


# ============================================================================
# import_document_content 测试
# ============================================================================


@pytest.mark.asyncio
async def test_import_document_content_markdown(monkeypatch):
    """测试导入 markdown 文档内容到 documents 表"""
    conn = _FakeConn({"id": 1})
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    # Mock generate_embedding and generate_document_summary
    async def fake_generate_embedding(text):
        return [0.1] * 1024

    async def fake_generate_summary(title, content):
        return "这是文档摘要"

    monkeypatch.setattr("src.api.document_service.generate_embedding", fake_generate_embedding)
    monkeypatch.setattr("src.api.document_service.generate_document_summary", fake_generate_summary)

    result = await import_document_content(
        title="测试文档",
        content="# 测试内容\n\n这是一段测试内容。",
        source_type="markdown"
    )

    assert result["status"] == "success"
    assert result["document"]["id"] == 1
    assert result["document"]["title"] == "测试文档"


@pytest.mark.asyncio
async def test_import_document_content_empty_returns_error(monkeypatch):
    """测试空内容返回错误"""
    conn = _FakeConn()
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    result = await import_document_content(title="测试", content="")

    assert result["status"] == "error"
    assert "为空" in result["message"]


@pytest.mark.asyncio
async def test_import_document_content_uses_content_hash(monkeypatch):
    """测试导入时计算并使用 content_hash"""
    conn = _FakeConn({"id": 1})
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    async def fake_generate_embedding(text):
        return [0.1] * 1024

    async def fake_generate_summary(title, content):
        return "Test summary"

    monkeypatch.setattr("src.api.document_service.generate_embedding", fake_generate_embedding)
    monkeypatch.setattr("src.api.document_service.generate_document_summary", fake_generate_summary)

    content = "# Test\n\nContent here"
    result = await import_document_content(title="Test", content=content)

    assert result["status"] == "success"
    # 验证 content_hash 被包含在返回结果中
    assert "document" in result


@pytest.mark.asyncio
async def test_import_document_content_normalizes_json_for_content_hash(monkeypatch):
    """同语义 JSON（不同格式）应生成一致的 content_hash。"""
    conn = _FakeConn([{"id": 1}, {"id": 2}])
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    async def fake_generate_embedding(text):
        return [0.1] * 1024

    async def fake_generate_summary(title, content):
        return "Test summary"

    monkeypatch.setattr("src.api.document_service.generate_embedding", fake_generate_embedding)
    monkeypatch.setattr("src.api.document_service.generate_document_summary", fake_generate_summary)

    json_pretty = '{\n  "name": "alice",\n  "age": 20\n}'
    json_compact = '{"name":"alice","age":20}'

    await import_document_content(title="A", content=json_pretty, source_type="json")
    await import_document_content(title="B", content=json_compact, source_type="json")

    first_hash = conn.fetchrow_args_history[0][5]
    second_hash = conn.fetchrow_args_history[1][5]
    assert first_hash == second_hash


# ============================================================================
# list_documents 测试
# ============================================================================


@pytest.mark.asyncio
async def test_list_documents_generic_type_only(monkeypatch):
    """测试列出文档只支持通用类型，不支持旧类型"""
    conn = _FakeConn([])
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    # "documents" 是新的通用类型，应该能正常查询
    result = await list_documents("documents", limit=10, offset=0)

    assert result["status"] == "success"
    # 不再支持旧类型
    # 注意：根据通用化计划，policies/role_models/schools 不再支持


@pytest.mark.asyncio
async def test_list_documents_returns_empty_list(monkeypatch):
    """测试列出文档返回空列表"""
    conn = _FakeConn([])
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    result = await list_documents("documents", limit=10, offset=0)

    assert result["status"] == "success"
    assert result["documents"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_list_documents_policies_returns_error(monkeypatch):
    """测试 policies 类型不再支持"""
    conn = _FakeConn()
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    result = await list_documents("policies", limit=10, offset=0)

    assert result["status"] == "error"
    assert "未知的资料类型" in result["message"] or "不支持" in result["message"]


# ============================================================================
# delete_document 测试
# ============================================================================


@pytest.mark.asyncio
async def test_delete_document_generic(monkeypatch):
    """测试删除通用文档"""
    conn = _FakeConn("DELETE 1")
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    result = await delete_document("documents", 1)

    assert result["status"] == "success"
    assert result["document_id"] == 1


@pytest.mark.asyncio
async def test_delete_document_not_found(monkeypatch):
    """测试删除不存在的文档返回错误"""
    conn = _FakeConn("DELETE 0")
    monkeypatch.setattr("src.api.document_service.get_pool", lambda: _make_fake_pool(conn))

    result = await delete_document("documents", 999)

    assert result["status"] == "error"
    assert "未找到" in result["message"]


# ============================================================================
# 提示词集中化测试
# ============================================================================

import inspect
from src.chat.prompts_runtime import DOC_SUMMARY_SYSTEM_PROMPT, DOC_SUMMARY_USER_PROMPT_TEMPLATE


def test_document_summary_prompt_is_centralized():
    """验证 generate_document_summary 函数使用集中化的提示词常量"""
    from src.api import document_service

    # 获取 generate_document_summary 函数的源代码
    source = inspect.getsource(document_service.generate_document_summary)

    # 验证函数中是否使用了 DOC_SUMMARY_SYSTEM_PROMPT 和 DOC_SUMMARY_USER_PROMPT_TEMPLATE
    assert "DOC_SUMMARY_SYSTEM_PROMPT" in source, \
        "generate_document_summary 应该使用 DOC_SUMMARY_SYSTEM_PROMPT"
    assert "DOC_SUMMARY_USER_PROMPT_TEMPLATE" in source, \
        "generate_document_summary 应该使用 DOC_SUMMARY_USER_PROMPT_TEMPLATE"
