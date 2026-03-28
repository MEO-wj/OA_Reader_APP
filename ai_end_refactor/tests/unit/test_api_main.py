import json
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_root_endpoint_returns_app_info():
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "AI Agent API", "version": "0.1.0"}


def test_health_endpoint_returns_ok_status():
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_skills_endpoint_returns_skill_list(monkeypatch):
    from src.api.main import app

    class _FakeSkillSystem:
        def __init__(self):
            self.available_skills = {
                "skill-a": SimpleNamespace(description="desc-a"),
                "skill-b": SimpleNamespace(description="desc-b"),
            }

        @classmethod
        async def create(cls, _config):
            return cls()

    monkeypatch.setattr("src.core.db_skill_system.DbSkillSystem", _FakeSkillSystem)

    client = TestClient(app)
    response = client.get("/skills")

    assert response.status_code == 200
    assert response.json() == {
        "skills": [
            {"name": "skill-a", "description": "desc-a"},
            {"name": "skill-b", "description": "desc-b"},
        ],
        "data_source": "database",
        "skill_count": 2,
    }


import pytest


@pytest.mark.asyncio
async def test_chat_endpoint_streams_sse_from_chat_service(monkeypatch):
    from src.api.main import chat
    from src.api.models import ChatRequest

    class _FakeMemoryDB:
        async def get_or_create_session(self, user_id: str, conversation_id: str | None = None):
            assert user_id == "test_user"
            assert conversation_id is None
            return "conv-default", "新会话"

    class _FakeChatService:
        def __init__(self, user_id: str | None = None, conversation_id: str | None = None):
            self.user_id = user_id
            self.conversation_id = conversation_id

        async def chat_stream(self, message: str):
            assert message == "hello"
            yield 'event: start\\ndata: {"type": "start"}\\n\\n'
            yield 'event: done\\ndata: {"type": "done", "usage": {}}\\n\\n'

    called = {}

    def _fake_get_chat_service(user_id: str | None = None, conversation_id: str | None = None):
        called["user_id"] = user_id
        called["conversation_id"] = conversation_id
        return _FakeChatService(user_id=user_id, conversation_id=conversation_id)

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)
    monkeypatch.setattr("src.api.main.get_chat_service", _fake_get_chat_service)

    response = await chat(ChatRequest(message="hello", user_id="test_user"))
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    body = "".join(chunks)

    assert "event: start" in body
    assert "event: done" in body
    assert called == {"user_id": "test_user", "conversation_id": "conv-default"}


@pytest.mark.asyncio
async def test_chat_endpoint_sets_conversation_header(monkeypatch):
    from src.api.main import chat
    from src.api.models import ChatRequest

    class _FakeMemoryDB:
        async def get_or_create_session(self, user_id: str, conversation_id: str | None = None):
            assert user_id == "u1"
            assert conversation_id == "conv-in"
            return "conv-in", "标题"

    class _FakeChatService:
        def __init__(self, user_id: str | None = None, conversation_id: str | None = None):
            self.user_id = user_id
            self.conversation_id = conversation_id

        async def chat_stream(self, _message: str):
            yield 'event: done\\ndata: {"type": "done"}\\n\\n'

    def _fake_get_chat_service(user_id: str | None = None, conversation_id: str | None = None):
        return _FakeChatService(user_id=user_id, conversation_id=conversation_id)

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)
    monkeypatch.setattr("src.api.main.get_chat_service", _fake_get_chat_service)

    response = await chat(ChatRequest(message="hello", user_id="u1", conversation_id="conv-in"))
    assert response.headers["x-conversation-id"] == "conv-in"


def test_list_sessions_endpoint(monkeypatch):
    from src.api.main import app

    class _FakeMemoryDB:
        async def list_sessions(self, user_id: str):
            assert user_id == "u1"
            return [{"user_id": "u1", "conversation_id": "c1", "title": "会话1"}]

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)

    client = TestClient(app)
    response = client.get("/chat/sessions", params={"user_id": "u1"})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["sessions"][0]["conversation_id"] == "c1"


def test_create_session_endpoint(monkeypatch):
    from src.api.main import app

    called = {}

    class _FakeMemoryDB:
        async def create_session(self, user_id: str, conversation_id: str, title: str):
            called["user_id"] = user_id
            called["conversation_id"] = conversation_id
            called["title"] = title

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)
    monkeypatch.setattr("src.api.main.uuid.uuid4", lambda: "12345678-aaaa-bbbb")

    client = TestClient(app)
    response = client.post("/chat/sessions", json={"user_id": "u1", "title": "考研咨询"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert called["user_id"] == "u1"
    assert called["title"] == "考研咨询"


def test_get_session_endpoint_returns_session_and_messages(monkeypatch):
    from src.api.main import app

    class _FakeMemoryDB:
        async def get_session(self, user_id: str, conversation_id: str):
            if conversation_id == "missing":
                return None
            return {"user_id": user_id, "conversation_id": conversation_id, "title": "会话"}

        async def get_conversation(self, user_id: str, conversation_id: str = "default"):
            assert user_id == "u1"
            assert conversation_id == "c1"
            return [{"role": "user", "content": "hi"}]

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)

    client = TestClient(app)
    ok_resp = client.get("/chat/sessions/c1", params={"user_id": "u1"})
    assert ok_resp.status_code == 200
    assert ok_resp.json()["session"]["conversation_id"] == "c1"
    assert len(ok_resp.json()["messages"]) == 1

    not_found = client.get("/chat/sessions/missing", params={"user_id": "u1"})
    assert not_found.status_code == 404


def test_delete_session_endpoint(monkeypatch):
    from src.api.main import app

    called = {}

    class _FakeMemoryDB:
        async def delete_session(self, user_id: str, conversation_id: str):
            called["user_id"] = user_id
            called["conversation_id"] = conversation_id

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)

    client = TestClient(app)
    response = client.delete("/chat/sessions/c1", params={"user_id": "u1"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert called == {"user_id": "u1", "conversation_id": "c1"}


def test_app_shutdown_closes_resources_in_order(monkeypatch):
    # 该用例只验证关闭顺序，不应受 .env 中 AUTO_MIGRATE=true 影响
    monkeypatch.setenv("AUTO_MIGRATE", "false")
    monkeypatch.setenv("AUTO_IMPORT", "false")

    from src.api.main import app

    calls = []

    monkeypatch.setattr("src.api.main.close_clients", lambda: calls.append("close_clients"))

    async def _close_resources():
        calls.append("close_resources")

    async def _close_pool():
        calls.append("close_pool")

    async def _close_api_queue():
        calls.append("close_api_queue")

    monkeypatch.setattr("src.api.main.close_resources", _close_resources)
    monkeypatch.setattr("src.api.main.close_pool", _close_pool)
    monkeypatch.setattr("src.api.main.close_api_queue", _close_api_queue)
    monkeypatch.setattr("src.api.main.shutdown_tool_loop", lambda: calls.append("shutdown_tool_loop"))

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert calls == [
        "close_clients",
        "close_resources",
        "close_pool",
        "close_api_queue",
        "shutdown_tool_loop",
    ]


def test_app_startup_runs_auto_migration_when_enabled(monkeypatch):
    from src.api.main import app

    monkeypatch.setenv("AUTO_MIGRATE", "true")

    called = {"run_migration": 0}

    async def _fake_run_migration(auto_repair: bool = False):
        called["run_migration"] += 1
        assert auto_repair is True
        return True

    monkeypatch.setattr("src.api.main.run_migration", _fake_run_migration)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert called["run_migration"] == 1


def test_app_startup_skips_import_when_decider_returns_false(monkeypatch):
    from src.api.main import app

    monkeypatch.setenv("AUTO_MIGRATE", "true")
    monkeypatch.setenv("AUTO_IMPORT", "true")

    called = {
        "run_migration": 0,
        "decider": 0,
        "skills": 0,
    }

    async def _fake_run_migration(auto_repair: bool = False):
        called["run_migration"] += 1
        return True

    async def _fake_decider():
        called["decider"] += 1
        return False

    async def _fake_import_skills(_path):
        called["skills"] += 1

    monkeypatch.setattr("src.api.main.run_migration", _fake_run_migration)
    monkeypatch.setattr("src.api.main.should_run_auto_import", _fake_decider)
    monkeypatch.setattr("src.api.main.import_skills_main", _fake_import_skills)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert called["run_migration"] == 1
    assert called["decider"] == 1
    assert called["skills"] == 0


def test_app_startup_runs_import_when_decider_returns_true(monkeypatch):
    from src.api.main import app

    monkeypatch.setenv("AUTO_MIGRATE", "true")
    monkeypatch.setenv("AUTO_IMPORT", "true")

    called = {"decider": 0, "skills": 0}

    async def _fake_run_migration(auto_repair: bool = False):
        return True

    async def _fake_decider():
        called["decider"] += 1
        return True

    async def _fake_import_skills(_path):
        called["skills"] += 1

    monkeypatch.setattr("src.api.main.run_migration", _fake_run_migration)
    monkeypatch.setattr("src.api.main.should_run_auto_import", _fake_decider)
    monkeypatch.setattr("src.api.main.import_skills_main", _fake_import_skills)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert called["decider"] == 1
    assert called["skills"] == 1


def test_get_chat_history_returns_messages(monkeypatch):
    from src.api.main import app

    class _FakeMemoryDB:
        async def get_conversation(self, user_id: str, conversation_id: str = "default"):
            assert user_id == "u1"
            assert conversation_id == "default"
            return [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好，我在"},
            ]

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)

    client = TestClient(app)
    response = client.get("/chat/history", params={"user_id": "u1"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "u1"
    assert len(response.json()["messages"]) == 2


def test_get_chat_users_returns_recent_users(monkeypatch):
    from src.api.main import app

    class _FakeMemoryDB:
        async def list_recent_users(self, limit: int = 20):
            assert limit == 5
            return [
                {"user_id": "u2", "updated_at": "2026-03-04T10:00:00"},
                {"user_id": "u1", "updated_at": "2026-03-04T09:00:00"},
            ]

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)

    client = TestClient(app)
    response = client.get("/chat/users", params={"limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["users"][0]["user_id"] == "u2"


def test_delete_chat_history_clears_user(monkeypatch):
    from src.api.main import app

    called = {"user_id": None}

    class _FakeMemoryDB:
        async def clear_user_memory(self, user_id: str):
            called["user_id"] = user_id

    monkeypatch.setattr("src.db.memory.MemoryDB", _FakeMemoryDB)

    client = TestClient(app)
    response = client.delete("/chat/history", params={"user_id": "u1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": "u1"}
    assert called["user_id"] == "u1"
