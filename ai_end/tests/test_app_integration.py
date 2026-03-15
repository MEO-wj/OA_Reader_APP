"""Flask API 集成测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(mock_config, mock_cache):
    """创建 Flask 测试客户端。"""
    import sys
    from pathlib import Path
    from unittest.mock import Mock, patch

    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))

    with patch("ai_end.config.Config") as MockConfig:
        mock_cfg = MockConfig.return_value
        mock_cfg.redis_host = "localhost"
        mock_cfg.redis_port = 6379
        mock_cfg.redis_db = 0
        mock_cfg.redis_password = None
        mock_cfg.embed_base_url = None
        mock_cfg.embed_api_key = None
        mock_cfg.ai_base_url = "https://api.example.com/v1"
        mock_cfg.ai_model = "gpt-3.5-turbo"
        mock_cfg.api_key = "sk-test"
        mock_cfg.ai_vector_limit_days = None
        mock_cfg.ai_vector_limit_count = None
        mock_cfg.ai_recency_half_life_days = 180.0
        mock_cfg.ai_recency_weight = 0.2
        mock_cfg.ai_models = []
        mock_cfg.ai_enable_load_balancing = False
        mock_cfg.ai_queue_enabled = False
        mock_cfg.ai_queue_max_size = 20
        mock_cfg.ai_queue_timeout = 30
        mock_cfg.flask_host = "0.0.0.0"
        mock_cfg.flask_port = 4421

        with patch("ai_end.app.config", mock_cfg):
            with patch("ai_end.app.redis_client") as mock_redis:
                mock_redis.ping.return_value = True

                with patch("ai_end.app.cache", mock_cache):
                    with patch("ai_end.app._load_balancer") as mock_lb:
                        mock_lb.models = []

                        with patch("ai_end.app.db_session") as mock_db:
                            with patch("ai_end.app._initialize_queue"):
                                from ai_end.app import app
                                app.config["TESTING"] = True

                                with app.test_client() as test_client:
                                    yield test_client


class TestHealthEndpoint:
    """健康检查端点测试。"""

    def test_health_check(self, client):
        """测试健康检查。"""
        response = client.get("/health")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ok"


class TestAskEndpoint:
    """问答端点测试。"""

    def test_ask_without_question(self, client):
        """测试不带问题。"""
        response = client.post(
            "/ask",
            data=json.dumps({}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_ask_with_question(self, client, monkeypatch):
        """测试带问题的请求。"""
        # Mock _execute_ai_request
        mock_execute = Mock(return_value={
            "answer": "test answer",
            "related_articles": []
        })
        monkeypatch.setattr("ai_end.app._execute_ai_request", mock_execute)

        # Mock _is_ai_configured
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({"question": "hello"}),
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_ask_with_top_k(self, client, monkeypatch):
        """测试带 top_k 的请求。"""
        mock_execute = Mock(return_value={
            "answer": "test",
            "related_articles": []
        })
        monkeypatch.setattr("ai_end.app._execute_ai_request", mock_execute)
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({"question": "test", "top_k": 5}),
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_ask_with_display_name(self, client, monkeypatch):
        """测试带 display_name 的请求。"""
        mock_execute = Mock(return_value={
            "answer": "test",
            "related_articles": []
        })
        monkeypatch.setattr("ai_end.app._execute_ai_request", mock_execute)
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({"question": "test", "display_name": "张三"}),
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_ask_not_configured(self, client, monkeypatch):
        """测试 AI 未配置。"""
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: False)

        response = client.post(
            "/ask",
            data=json.dumps({"question": "hello"}),
            content_type="application/json",
        )

        assert response.status_code == 500


class TestClearMemoryEndpoint:
    """清空记忆端点测试。"""

    def test_clear_memory_without_user_id(self, client):
        """测试不带 user_id。"""
        response = client.post(
            "/clear_memory",
            data=json.dumps({}),
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_clear_memory_with_user_id(self, client, mock_cache):
        """测试带 user_id。"""
        response = client.post(
            "/clear_memory",
            data=json.dumps({"user_id": "user123"}),
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_clear_memory_no_cache(self, client, monkeypatch):
        """测试无缓存情况。"""
        monkeypatch.setattr("ai_end.app.cache", None)

        response = client.post(
            "/clear_memory",
            data=json.dumps({"user_id": "user123"}),
            content_type="application/json",
        )

        assert response.status_code == 200


class TestEmbedEndpoint:
    """嵌入端点测试。"""

    def test_embed_without_text(self, client):
        """测试不带 text。"""
        response = client.post(
            "/embed",
            data=json.dumps({}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_embed_success(self, client, monkeypatch):
        """测试嵌入成功。"""
        monkeypatch.setattr("ai_end.app.generate_embedding", lambda text: [0.1, 0.2, 0.3])

        response = client.post(
            "/embed",
            data=json.dumps({"text": "hello"}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["embedding"] == [0.1, 0.2, 0.3]

    def test_embed_failed(self, client, monkeypatch):
        """测试嵌入失败。"""
        monkeypatch.setattr("ai_end.app.generate_embedding", lambda text: None)

        response = client.post(
            "/embed",
            data=json.dumps({"text": "hello"}),
            content_type="application/json",
        )

        assert response.status_code == 503
        data = json.loads(response.data)
        assert "error" in data


class TestAskEndpointWithQueue:
    """队列模式下的问答端点测试。"""

    def test_ask_with_queue_enabled(self, client, monkeypatch):
        """测试启用队列。"""
        # Mock queue
        mock_queue = Mock()
        mock_queue.enqueue.return_value = (True, {"answer": "queued response"})
        monkeypatch.setattr("ai_end.app._ai_queue", mock_queue)

        # Mock config
        mock_cfg = Mock()
        mock_cfg.ai_queue_enabled = True
        monkeypatch.setattr("ai_end.app.config", mock_cfg)
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({"question": "test"}),
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_ask_queue_full(self, client, monkeypatch):
        """测试队列满。"""
        mock_queue = Mock()
        mock_queue.enqueue.return_value = (False, "服务繁忙，请稍后再试")
        monkeypatch.setattr("ai_end.app._ai_queue", mock_queue)

        mock_cfg = Mock()
        mock_cfg.ai_queue_enabled = True
        monkeypatch.setattr("ai_end.app.config", mock_cfg)
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({"question": "test"}),
            content_type="application/json",
        )

        assert response.status_code == 503


class TestCORS:
    """CORS 测试。"""

    def test_cors_headers(self, client):
        """测试 CORS 头。"""
        response = client.options("/health")

        # Flask-CORS 可能会处理 OPTIONS 请求
        assert response.status_code in [200, 405]


class TestAskEndpointEdgeCases:
    """问答端点边界情况测试。"""

    def test_ask_with_extra_fields(self, client, monkeypatch):
        """测试额外字段。"""
        mock_execute = Mock(return_value={
            "answer": "test",
            "related_articles": []
        })
        monkeypatch.setattr("ai_end.app._execute_ai_request", mock_execute)
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({
                "question": "test",
                "extra_field": "ignored",
                "another_field": 123
            }),
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_ask_with_user_id(self, client, monkeypatch):
        """测试带 user_id。"""
        mock_execute = Mock(return_value={
            "answer": "test",
            "related_articles": []
        })
        monkeypatch.setattr("ai_end.app._execute_ai_request", mock_execute)
        monkeypatch.setattr("ai_end.app._is_ai_configured", lambda: True)

        response = client.post(
            "/ask",
            data=json.dumps({
                "question": "test",
                "user_id": "user123"
            }),
            content_type="application/json",
        )

        assert response.status_code == 200
