"""API 分层队列测试。"""

import asyncio
import pytest


def test_get_api_queue_recreates_when_event_loop_changes(monkeypatch):
    from src.core import api_queue as api_queue_module

    api_queue_module._api_queue = None
    api_queue_module._api_queue_loop = None

    loop_calls = {"count": 0}
    loop_a = object()
    loop_b = object()

    def fake_get_running_loop():
        loop_calls["count"] += 1
        if loop_calls["count"] == 1:
            return loop_a
        return loop_b

    monkeypatch.setattr(api_queue_module.asyncio, "get_running_loop", fake_get_running_loop)

    q1 = api_queue_module.get_api_queue()
    q2 = api_queue_module.get_api_queue()

    assert q1 is not q2


@pytest.mark.asyncio
async def test_submit_async_supports_async_generator():
    from src.core.api_queue import APIQueue

    queue = APIQueue(llm_concurrency=1, embedding_concurrency=1, rerank_concurrency=1)

    async def fake_stream():
        yield "a"
        yield "b"

    stream = await queue.submit_async("llm", fake_stream)
    items = []
    async for chunk in stream:
        items.append(chunk)

    assert items == ["a", "b"]
    await queue.close()


def test_submit_reinitializes_workers_when_event_loop_changes():
    """同一个 APIQueue 跨事件循环复用时，submit 不应卡住。"""
    from src.core.api_queue import APIQueue

    queue = APIQueue(llm_concurrency=1, embedding_concurrency=1, rerank_concurrency=1)

    async def first_loop_submit():
        return await queue.submit("llm", lambda: "ok-first")

    async def second_loop_submit():
        return await asyncio.wait_for(
            queue.submit("llm", lambda: "ok-second"),
            timeout=2,
        )

    assert asyncio.run(first_loop_submit()) == "ok-first"
    assert asyncio.run(second_loop_submit()) == "ok-second"
