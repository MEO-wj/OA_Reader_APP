"""
TDD GREEN 阶段: 旧 AI End 兼容接口集成测试

验证 /ask、/clear_memory、/embed 三个兼容端点的契约和内容类型。
"""

from fastapi.testclient import TestClient


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
