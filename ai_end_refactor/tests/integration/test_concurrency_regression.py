"""并发回归测试。"""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_concurrent_search_and_chat_no_unhandled_concurrency_errors(
    monkeypatch, tmp_path
):
    from src.chat.client import ChatClient
    from src.config import Config
    from src.core import api_clients
    from src.core import api_queue as api_queue_module
    from src.core import article_retrieval

    api_clients.close_clients()
    api_queue_module._api_queue = None

    class FakeConn:
        def __init__(self):
            self.busy = False

        async def fetch(self, *args, **kwargs):
            if self.busy:
                raise Exception("another operation is in progress")
            self.busy = True
            await asyncio.sleep(0.02)
            self.busy = False
            return []

    fake_conn = FakeConn()

    class AcquireCtx:
        async def __aenter__(self):
            return fake_conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def acquire(self):
            return AcquireCtx()

    async def fake_get_pool():
        return FakePool()

    monkeypatch.setattr(article_retrieval, "get_pool", fake_get_pool)
    monkeypatch.setattr(article_retrieval, "_generate_embedding_sync", lambda text: [0.1, 0.2])

    class FakeLLMClient:
        def __init__(self):
            message = type("Message", (), {"content": "ok", "tool_calls": None})
            choice = type("Choice", (), {"message": message})
            self._response = type("Resp", (), {"choices": [choice]})
            self.chat = type(
                "Chat",
                (),
                {"completions": type("Completions", (), {"create": self._create})},
            )()

        def _create(self, **kwargs):
            return self._response

    monkeypatch.setattr("src.chat.client.get_llm_client", lambda *args, **kwargs: FakeLLMClient())

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    config = Config(
        api_key="",
        base_url="https://api.openai.com/v1",
        model="gpt-4",
        skills_dir=str(skills_dir),
    )
    client = ChatClient(config)

    searches = [article_retrieval.search_articles(f"q-{i}") for i in range(3)]
    chat_call = asyncio.to_thread(client.chat, "规培几年")
    outputs = await asyncio.gather(*searches, chat_call, return_exceptions=True)

    for out in outputs:
        assert not isinstance(out, Exception)

    for out in outputs[:-1]:
        assert isinstance(out, dict)
        assert "results" in out or "error" in out
        if "error" in out:
            assert "another operation is in progress" not in out["error"]
            assert "Event loop is closed" not in out["error"]
