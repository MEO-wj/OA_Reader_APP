# tests/acceptance/test_sse_collector.py
import pytest
from tests.acceptance.utils.sse_collector import SSEEventCollector


class _MockAsyncContextManager:
    """模拟异步上下文管理器"""
    def __init__(self, iterator):
        self._iterator = iterator

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aiter_text(self):
        async for item in self._iterator:
            yield item


class _MockClient:
    """模拟 httpx.AsyncClient"""
    def __init__(self, iterator):
        self._iterator = iterator

    def stream(self, *args, **kwargs):
        return _MockAsyncContextManager(self._iterator)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_collect_basic_events(monkeypatch):
    """测试收集基本 SSE 事件"""

    async def _fake_stream():
        yield "event: start\n\ndata: {\"type\": \"start\"}\n\n"
        yield "event: delta\n\ndata: {\"content\": \"你好\"}\n\n"
        yield "event: delta\n\ndata: {\"content\": \"，世界\"}\n\n"
        yield "event: done\n\ndata: {\"usage\": {\"total_tokens\": 10}}\n\n"

    monkeypatch.setattr(
        "tests.acceptance.utils.sse_collector.httpx.AsyncClient",
        lambda: _MockClient(_fake_stream())
    )

    collector = SSEEventCollector()
    result = await collector.collect_chat_events("http://test", "你好")

    # 验证基础结构
    assert "start_time" in result
    assert "end_time" in result
    assert "duration_ms" in result
    assert result["request"]["message"] == "你好"

    # 验证事件 - delta 应该合并成一条
    assert len(result["events"]) == 3  # start, delta(合并), done
    assert result["events"][0]["type"] == "start"
    assert result["events"][1]["type"] == "delta"
    # delta 内容应该是合并后的完整内容
    assert result["events"][1]["content"] == "你好，世界"
    assert result["events"][2]["type"] == "done"

    # 验证回复
    assert result["response"] == "你好，世界"

    # 验证 token 消耗
    assert result["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_collect_skill_and_tool_calls(monkeypatch):
    """测试收集技能调用和工具调用"""

    async def _fake_stream():
        yield "event: start\n\ndata: {\"type\": \"start\"}\n\n"
        yield 'event: skill_call\n\ndata: {"skill": "test-skill", "description": "测试技能"}\n\n'
        yield 'event: tool_call\n\ndata: {"tool": "test-tool", "arguments": "{\\"query\\": \\"test\\"}"}\n\n'
        yield 'event: tool_result\n\ndata: {"tool": "test-tool", "result": "{\\"status\\": \\"ok\\"}"}\n\n'
        yield "event: delta\n\ndata: {\"content\": \"回复内容\"}\n\n"
        yield "event: done\n\ndata: {\"usage\": {\"total_tokens\": 100}}\n\n"

    monkeypatch.setattr(
        "tests.acceptance.utils.sse_collector.httpx.AsyncClient",
        lambda: _MockClient(_fake_stream())
    )

    collector = SSEEventCollector()
    result = await collector.collect_chat_events("http://test", "test")

    # 验证技能调用
    assert "test-skill" in result["skills_called"]

    # 验证工具调用（包含参数和结果）
    assert len(result["tools_called"]) == 1
    assert result["tools_called"][0]["name"] == "test-tool"
    assert result["tools_called"][0]["arguments"] == '{"query": "test"}'
    assert result["tools_called"][0]["result"] == '{"status": "ok"}'

    # 验证事件记录
    skill_event = next(e for e in result["events"] if e["type"] == "skill_call")
    assert skill_event["skill"] == "test-skill"
    assert skill_event["description"] == "测试技能"

    tool_call_event = next(e for e in result["events"] if e["type"] == "tool_call")
    assert tool_call_event["tool"] == "test-tool"

    tool_result_event = next(e for e in result["events"] if e["type"] == "tool_result")
    assert tool_result_event["tool"] == "test-tool"
    assert tool_result_event["result"] == '{"status": "ok"}'


@pytest.mark.asyncio
async def test_collect_with_timestamps(monkeypatch):
    """测试时间戳记录"""

    async def _fake_stream():
        yield "event: start\n\ndata: {\"type\": \"start\"}\n\n"
        yield "event: done\n\ndata: {\"usage\": {}}\n\n"

    monkeypatch.setattr(
        "tests.acceptance.utils.sse_collector.httpx.AsyncClient",
        lambda: _MockClient(_fake_stream())
    )

    collector = SSEEventCollector()
    result = await collector.collect_chat_events("http://test", "test")

    # 验证时间格式
    assert "T" in result["start_time"]  # ISO 格式
    assert "T" in result["end_time"]
    assert result["duration_ms"] >= 0

    # 验证事件时间戳
    for event in result["events"]:
        assert "timestamp" in event
        assert "T" in event["timestamp"]


@pytest.mark.asyncio
async def test_collect_db_operation(monkeypatch):
    """测试数据库操作事件收集"""

    async def _fake_stream():
        yield "event: start\n\ndata: {\"type\": \"start\"}\n\n"
        yield 'event: db_operation\n\ndata: {"operation": "search_documents", "message": "正在调用数据库: search_documents"}\n\n'
        yield "event: done\n\ndata: {\"usage\": {}}\n\n"

    monkeypatch.setattr(
        "tests.acceptance.utils.sse_collector.httpx.AsyncClient",
        lambda: _MockClient(_fake_stream())
    )

    collector = SSEEventCollector()
    result = await collector.collect_chat_events("http://test", "test")

    # 验证数据库操作事件
    db_event = next(e for e in result["events"] if e["type"] == "db_operation")
    assert db_event["operation"] == "search_documents"
    assert db_event["message"] == "正在调用数据库: search_documents"


@pytest.mark.asyncio
async def test_collect_error_event(monkeypatch):
    """测试错误事件收集"""

    async def _fake_stream():
        yield "event: start\n\ndata: {\"type\": \"start\"}\n\n"
        yield 'event: error\n\ndata: {"message": "发生错误"}\n\n'

    monkeypatch.setattr(
        "tests.acceptance.utils.sse_collector.httpx.AsyncClient",
        lambda: _MockClient(_fake_stream())
    )

    collector = SSEEventCollector()
    result = await collector.collect_chat_events("http://test", "test")

    # 验证错误事件
    error_event = next(e for e in result["events"] if e["type"] == "error")
    assert error_event["error"] == "发生错误"
