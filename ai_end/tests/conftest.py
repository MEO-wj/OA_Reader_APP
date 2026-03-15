"""pytest fixtures 和测试配置。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

# 确保能找到 ai_end 模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_db_session():
    """Mock 数据库会话。"""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

    mock_cursor.fetchall.return_value = []

    session = Mock()
    session.__enter__ = Mock(return_value=mock_conn)
    session.__exit__ = Mock(return_value=False)

    return session


@pytest.fixture
def mock_config():
    """Mock 配置对象。"""
    config = Mock()
    config.embed_base_url = "https://api.example.com/v1/embeddings"
    config.embed_model = "text-embedding-3-small"
    config.embed_api_key = "sk-test-key"
    config.embed_dim = 1024
    config.ai_base_url = "https://api.example.com/v1"
    config.ai_model = "gpt-3.5-turbo"
    config.api_key = "sk-test-key"
    config.ai_vector_limit_days = 30
    config.ai_vector_limit_count = 10
    config.ai_recency_half_life_days = 180.0
    config.ai_recency_weight = 0.2
    config.ai_models = []
    config.ai_enable_load_balancing = False
    config.ai_queue_enabled = True
    config.ai_queue_max_size = 20
    config.ai_queue_timeout = 30
    config.flask_host = "0.0.0.0"
    config.flask_port = 4421
    return config


@pytest.fixture
def sample_model_config():
    """示例模型配置。"""
    from ai_end.services.load_balancer import ModelConfig

    return ModelConfig(
        api_key="sk-test-key-1234567890",
        base_url="https://api.example.com/v1",
        model="gpt-3.5-turbo",
    )


@pytest.fixture
def sample_articles():
    """示例文章数据。"""
    return [
        {
            "id": 1,
            "title": "测试通知1",
            "unit": "教务处",
            "published_on": "2024-01-15",
            "summary": "这是测试摘要1",
            "content": "这是测试内容1",
            "similarity": 0.95,
            "score": 0.9,
        },
        {
            "id": 2,
            "title": "测试通知2",
            "unit": "学生处",
            "published_on": "2024-01-10",
            "summary": "这是测试摘要2",
            "content": "这是测试内容2",
            "similarity": 0.85,
            "score": 0.8,
        },
    ]


@pytest.fixture
def app_context(mock_config, mock_cache, mock_db_session, monkeypatch):
    """创建 Flask 应用测试上下文。"""
    import sys
    from pathlib import Path
    from unittest.mock import Mock, patch

    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))

    # Mock config
    monkeypatch.setattr("ai_end.config.Config", lambda: mock_config)

    # Mock db_session
    monkeypatch.setattr("ai_end.app.db_session", mock_db_session)

    # Mock load_balancer
    mock_lb = Mock()
    mock_lb.models = []
    monkeypatch.setattr("ai_end.app._load_balancer", mock_lb)

    # Mock cached agents
    monkeypatch.setattr("ai_end.app._cached_agents", {})

    return {
        "config": mock_config,
        "cache": mock_cache,
        "db_session": mock_db_session,
    }
