"""
TDD GREEN 阶段: 旧 AI End 兼容接口集成测试

验证 /ask、/clear_memory、/embed 三个兼容端点的契约和内容类型。
"""

from fastapi.testclient import TestClient

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"


# ---------------------------------------------------------------------------
# 请求验证契约测试（RED 阶段遗留）
# ---------------------------------------------------------------------------


def test_ask_returns_400_when_question_missing():
    from src.api.main import app

    client = TestClient(app)

    resp = client.post("/ask", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "请求参数错误，缺少question字段"}


def test_clear_memory_returns_400_when_user_id_missing():
    from src.api.main import app

    client = TestClient(app)

    resp = client.post("/clear_memory", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "用户信息缺失"}


def test_embed_returns_400_when_text_missing():
    from src.api.main import app

    client = TestClient(app)

    resp = client.post("/embed", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "请求参数错误，缺少text字段"}


# ---------------------------------------------------------------------------
# GREEN 阶段: content-type 断言测试
# ---------------------------------------------------------------------------


async def _mock_ask(self, **kwargs):
    """CompatService.ask 的 mock 实现，避免真实依赖。"""
    return {"answer": "mock", "related_articles": []}


def test_ask_returns_application_json_content_type(monkeypatch):
    """兼容接口必须返回 application/json，不能返回 SSE。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "ask", _mock_ask)
    client = TestClient(app)

    resp = client.post("/ask", json={"question": "测试"})

    assert resp.headers["content-type"].startswith("application/json")
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "related_articles" in data


# ---------------------------------------------------------------------------
# /embed 成功与失败语义测试
# ---------------------------------------------------------------------------


async def _mock_embed(self, text: str):
    """CompatService.embed 的 mock 实现，避免真实 API 调用。"""
    return [0.1, 0.2, 0.3]


def test_embed_success(monkeypatch):
    """embed 成功时返回 embedding 向量列表。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "embed", _mock_embed)
    client = TestClient(app)

    resp = client.post("/embed", json={"text": "hello"})

    assert resp.status_code == 200
    assert resp.json()["embedding"] == [0.1, 0.2, 0.3]


def test_embed_returns_application_json_content_type(monkeypatch):
    """embed 接口必须返回 application/json。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    async def _mock_embed_short(self, text):
        return [0.1, 0.2]

    monkeypatch.setattr(CompatService, "embed", _mock_embed_short)
    client = TestClient(app)

    resp = client.post("/embed", json={"text": "test"})
    assert resp.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# 成功路径测试（I5）
# ---------------------------------------------------------------------------


async def _mock_clear_memory(self, user_id: str | None = None):
    """CompatService.clear_memory 的 mock 实现。"""
    return {"cleared": True, "conversation_id": "mock-session-id"}


def test_clear_memory_success(monkeypatch):
    """clear_memory 成功时返回 200 和 cleared + conversation_id。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "clear_memory", _mock_clear_memory)
    client = TestClient(app)

    resp = client.post("/clear_memory", json={"user_id": VALID_UUID})

    assert resp.status_code == 200
    data = resp.json()
    assert data["cleared"] is True
    assert "conversation_id" in data


async def _mock_ask_with_session(self, **kwargs):
    """CompatService.ask 的 mock 实现，返回带会话信息的结果。"""
    return {
        "answer": "mock answer",
        "related_articles": [{"title": "test"}],
        "conversation_id": "mock-conv-id",
        "session_created": True,
    }


def test_ask_with_user_id_success(monkeypatch):
    """ask 携带 user_id 时返回 200 和会话字段。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "ask", _mock_ask_with_session)
    client = TestClient(app)

    resp = client.post("/ask", json={"question": "测试", "user_id": VALID_UUID})

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "related_articles" in data
    assert data["conversation_id"] == "mock-conv-id"
    assert data["session_created"] is True


def test_ask_forwards_conversation_id(monkeypatch):
    """/ask 应将调用方传入的 conversation_id 继续传给 CompatService.ask。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    captured: dict[str, object] = {}

    async def _mock_ask_capture(self, **kwargs):
        captured.update(kwargs)
        return {"answer": "mock", "related_articles": [], "conversation_id": "conv-9"}

    monkeypatch.setattr(CompatService, "ask", _mock_ask_capture)
    client = TestClient(app)

    resp = client.post(
        "/ask",
        json={
            "question": "测试",
            "user_id": VALID_UUID,
            "conversation_id": "conv-9",
        },
    )

    assert resp.status_code == 200
    assert captured["conversation_id"] == "conv-9"


# ---------------------------------------------------------------------------
# 异常处理测试（C1）
# ---------------------------------------------------------------------------


async def _mock_ask_raise(self, **kwargs):
    """CompatService.ask mock: 模拟下游异常。"""
    raise RuntimeError("LLM service unavailable")


async def _mock_clear_memory_raise(self, user_id=None):
    """CompatService.clear_memory mock: 模拟数据库异常。"""
    raise ConnectionError("Database connection failed")


async def _mock_embed_raise(self, text: str):
    """CompatService.embed mock: 模拟 API 异常。"""
    raise TimeoutError("Embedding API timeout")


def test_ask_returns_500_on_exception(monkeypatch):
    """C1: /ask 下游异常时应返回 500 + {"error": "..."}。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "ask", _mock_ask_raise)
    client = TestClient(app)

    resp = client.post("/ask", json={"question": "test"})

    assert resp.status_code == 500
    assert "error" in resp.json()


def test_clear_memory_returns_500_on_exception(monkeypatch):
    """C1: /clear_memory 下游异常时应返回 500 + {"error": "..."}。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "clear_memory", _mock_clear_memory_raise)
    client = TestClient(app)

    resp = client.post("/clear_memory", json={"user_id": VALID_UUID})

    assert resp.status_code == 500
    assert "error" in resp.json()


def test_embed_returns_500_on_exception(monkeypatch):
    """C1: /embed 下游异常时应返回 500 + {"error": "..."}。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "embed", _mock_embed_raise)
    client = TestClient(app)

    resp = client.post("/embed", json={"text": "hello"})

    assert resp.status_code == 500
    assert "error" in resp.json()
