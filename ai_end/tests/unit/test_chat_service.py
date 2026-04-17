import pytest


@pytest.mark.asyncio
async def test_sse_event_format(monkeypatch):
    from src.api.chat_service import ChatService

    class _FakeClient:
        async def chat_stream_async(self, _user_input: str):
            if False:
                yield {}

    async def _fake_create(_config, _user_id, _conversation_id, user_profile=None):
        return _FakeClient()

    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService()
    event = service._sse_event("delta", {"type": "delta", "content": "你好"})

    assert event.startswith("event: delta\n")
    assert "\n\n" in event
    assert '"content": "你好"' in event


@pytest.mark.asyncio
async def test_chat_stream_emits_start_and_forwards_events(monkeypatch):
    from src.api.chat_service import ChatService

    class _FakeClient:
        async def chat_stream_async(self, _user_input: str):
            yield {"type": "delta", "content": "A"}
            yield {"type": "done", "usage": {"total_tokens": 1}}

    async def _fake_create(_config, _user_id, _conversation_id, user_profile=None):
        return _FakeClient()

    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService(conversation_id="conv1")
    chunks = []
    async for chunk in service.chat_stream("test"):
        chunks.append(chunk)

    assert chunks[0].startswith("event: start")
    assert '"conversation_id": "conv1"' in chunks[0]
    assert "event: delta" in "".join(chunks)
    assert "event: done" in "".join(chunks)


@pytest.mark.asyncio
async def test_chat_stream_emits_error_event_on_exception(monkeypatch):
    from src.api.chat_service import ChatService

    class _FakeClient:
        async def chat_stream_async(self, _user_input: str):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    async def _fake_create(_config, _user_id, _conversation_id, user_profile=None):
        return _FakeClient()

    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService()
    chunks = []
    async for chunk in service.chat_stream("test"):
        chunks.append(chunk)

    full = "".join(chunks)
    assert "event: error" in full
    assert "boom" in full


@pytest.mark.asyncio
async def test_chat_stream_reuses_client_without_per_request_cleanup(monkeypatch):
    from src.api.chat_service import ChatService

    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def chat_stream_async(self, _user_input: str):
            if self.closed:
                raise RuntimeError("client closed")
            yield {"type": "done"}

        async def close(self):
            self.closed = True

    created_clients = []

    async def _fake_create(_config, _user_id, _conversation_id, user_profile=None):
        client = _FakeClient()
        created_clients.append(client)
        return client

    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService()

    first_chunks = []
    async for chunk in service.chat_stream("first"):
        first_chunks.append(chunk)
    second_chunks = []
    async for chunk in service.chat_stream("second"):
        second_chunks.append(chunk)

    assert len(created_clients) == 1
    assert created_clients[0].closed is False
    assert "event: error" not in "".join(first_chunks)
    assert "event: error" not in "".join(second_chunks)


@pytest.mark.asyncio
async def test_chat_service_initializes_user_memory_before_create(monkeypatch):
    from src.api.chat_service import ChatService

    called = {"ensure": 0, "user_id": None}

    class _FakeMemoryDB:
        async def ensure_user_exists(self, user_id: str):
            called["ensure"] += 1
            called["user_id"] = user_id

    class _FakeClient:
        async def chat_stream_async(self, _user_input: str):
            yield {"type": "done", "usage": {}}

    async def _fake_create(_config, _user_id, _conversation_id, user_profile=None):
        return _FakeClient()

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)
    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService(user_id=" new_user ")
    chunks = []
    async for chunk in service.chat_stream("hi"):
        chunks.append(chunk)

    assert called["ensure"] == 1
    assert called["user_id"] == "new_user"
    assert "event: done" in "".join(chunks)


@pytest.mark.asyncio
async def test_chat_service_passes_conversation_id_to_chat_client(monkeypatch):
    from src.api.chat_service import ChatService

    captured = {"conversation_id": None}

    class _FakeMemoryDB:
        async def ensure_user_exists(self, _user_id: str):
            return None

    class _FakeClient:
        async def chat_stream_async(self, _user_input: str):
            yield {"type": "done", "usage": {}}

    async def _fake_create(_config, _user_id, conversation_id, user_profile=None):
        captured["conversation_id"] = conversation_id
        return _FakeClient()

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)
    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService(user_id="u1", conversation_id="conv-xyz")
    async for _ in service.chat_stream("hello"):
        pass

    assert captured["conversation_id"] == "conv-xyz"


@pytest.mark.asyncio
async def test_chat_service_uses_di_create_chat_client(monkeypatch):
    from src.api.chat_service import ChatService

    captured = {"called": 0, "user_id": None, "conversation_id": None}

    class _FakeMemoryDB:
        async def ensure_user_exists(self, _user_id: str):
            return None

    class _FakeClient:
        async def chat_stream_async(self, _user_input: str):
            yield {"type": "done", "usage": {}}

    async def _fake_create(config, user_id, conversation_id, user_profile=None):
        captured["called"] += 1
        captured["user_id"] = user_id
        captured["conversation_id"] = conversation_id
        assert config is not None
        return _FakeClient()

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)
    monkeypatch.setattr("src.api.chat_service.create_chat_client", _fake_create)

    service = ChatService(user_id="u1", conversation_id="conv-xyz")
    async for _ in service.chat_stream("hello"):
        pass

    assert captured["called"] == 1
    assert captured["user_id"] == "u1"
    assert captured["conversation_id"] == "conv-xyz"
