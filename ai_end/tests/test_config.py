"""配置加载测试。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_end.config import Config


class TestConfigDefaults:
    """测试配置默认值。"""

    def test_default_redis_config(self):
        """测试 Redis 默认配置。"""
        config = Config(env_file="/nonexistent.env")
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert config.redis_password is None

    def test_default_embed_config(self):
        """测试 Embedding 默认配置。"""
        config = Config(env_file="/nonexistent.env")
        assert config.embed_base_url is None
        assert config.embed_model is None
        assert config.embed_api_key is None
        assert config.embed_dim == 1024

    def test_default_ai_config(self):
        """测试 AI 默认配置。"""
        config = Config(env_file="/nonexistent.env")
        assert config.ai_base_url is None
        assert config.ai_model is None
        assert config.api_key is None
        assert config.ai_vector_limit_days is None
        assert config.ai_vector_limit_count is None
        assert config.ai_recency_half_life_days == 180.0
        assert config.ai_recency_weight == 0.2

    def test_default_load_balancer_config(self):
        """测试负载均衡默认配置。"""
        config = Config(env_file="/nonexistent.env")
        assert config.ai_models == []
        assert config.ai_enable_load_balancing is True

    def test_default_queue_config(self):
        """测试队列默认配置。"""
        config = Config(env_file="/nonexistent.env")
        assert config.ai_queue_enabled is True
        assert config.ai_queue_max_size == 20
        assert config.ai_queue_timeout == 30

    def test_default_flask_config(self):
        """测试 Flask 默认配置。"""
        config = Config(env_file="/nonexistent.env")
        assert config.flask_host == "0.0.0.0"
        assert config.flask_port == 4421


class TestConfigEnvFileLoading:
    """测试环境文件加载。"""

    def test_load_redis_config_from_env_file(self, tmp_path):
        """测试从环境文件加载 Redis 配置。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "REDIS_HOST=redis.example.com\n"
            "REDIS_PORT=6380\n"
            "REDIS_DB=1\n"
            "REDIS_PASSWORD=testpass\n"
        )

        config = Config(env_file=str(env_file))
        assert config.redis_host == "redis.example.com"
        assert config.redis_port == 6380
        assert config.redis_db == 1
        assert config.redis_password == "testpass"

    def test_load_ai_config_from_env_file(self, tmp_path):
        """测试从环境文件加载 AI 配置。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AI_BASE_URL=https://api.openai.com/v1\n"
            "AI_MODEL=gpt-4\n"
            "API_KEY=sk-test123\n"
        )

        config = Config(env_file=str(env_file))
        assert config.ai_base_url == "https://api.openai.com/v1"
        assert config.ai_model == "gpt-4"
        assert config.api_key == "sk-test123"

    def test_load_embed_config_from_env_file(self, tmp_path):
        """测试从环境文件加载 Embedding 配置。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "EMBED_BASE_URL=https://api.openai.com/v1\n"
            "EMBED_MODEL=text-embedding-3-small\n"
            "EMBED_API_KEY=sk-embed123\n"
            "EMBED_DIM=1536\n"
        )

        config = Config(env_file=str(env_file))
        assert config.embed_base_url == "https://api.openai.com/v1"
        assert config.embed_model == "text-embedding-3-small"
        assert config.embed_api_key == "sk-embed123"
        assert config.embed_dim == 1536

    def test_load_queue_config_from_env_file(self, tmp_path):
        """测试从环境文件加载队列配置。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AI_QUEUE_ENABLED=false\n"
            "AI_QUEUE_MAX_SIZE=50\n"
            "AI_QUEUE_TIMEOUT=60\n"
        )

        config = Config(env_file=str(env_file))
        assert config.ai_queue_enabled is False
        assert config.ai_queue_max_size == 50
        assert config.ai_queue_timeout == 60

    def test_load_flask_config_from_env_file(self, tmp_path):
        """测试从环境文件加载 Flask 配置。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "FLASK_HOST=127.0.0.1\n"
            "FLASK_PORT=5000\n"
        )

        config = Config(env_file=str(env_file))
        assert config.flask_host == "127.0.0.1"
        assert config.flask_port == 5000


class TestConfigEnvVarOverride:
    """测试环境变量覆盖。"""

    def test_env_var_override_redis(self, monkeypatch):
        """测试环境变量覆盖 Redis 配置。"""
        monkeypatch.setenv("REDIS_HOST", "env-redis.example.com")
        monkeypatch.setenv("REDIS_PORT", "6381")

        config = Config(env_file="/nonexistent.env")
        assert config.redis_host == "env-redis.example.com"
        assert config.redis_port == 6381

    def test_env_var_override_ai(self, monkeypatch):
        """测试环境变量覆盖 AI 配置。"""
        monkeypatch.setenv("AI_MODEL", "gpt-4-turbo")
        monkeypatch.setenv("API_KEY", "sk-env-override")

        config = Config(env_file="/nonexistent.env")
        assert config.ai_model == "gpt-4-turbo"
        assert config.api_key == "sk-env-override"

    def test_env_var_override_load_balancer(self, monkeypatch):
        """测试环境变量覆盖负载均衡配置。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["glm-4"]},
            {"api_key": "sk-key2", "base_url": "https://api2.com/v1", "models": ["qwen-max"]},
        ]
        monkeypatch.setenv("AI_MODELS", json.dumps(models_config))
        monkeypatch.setenv("AI_ENABLE_LOAD_BALANCING", "false")

        config = Config(env_file="/nonexistent.env")
        assert len(config.ai_models) == 2
        assert config.ai_enable_load_balancing is False


class TestConfigInvalidValues:
    """测试无效值处理。"""

    def test_invalid_redis_port(self, tmp_path):
        """测试无效的 Redis 端口。"""
        env_file = tmp_path / ".env"
        env_file.write_text("REDIS_PORT=invalid\n")

        config = Config(env_file=str(env_file))
        assert config.redis_port == 6379  # 应该保持默认值

    def test_invalid_ai_queue_max_size(self, tmp_path):
        """测试无效的队列大小。"""
        env_file = tmp_path / ".env"
        env_file.write_text("AI_QUEUE_MAX_SIZE=abc\n")

        config = Config(env_file=str(env_file))
        assert config.ai_queue_max_size == 20  # 应该保持默认值

    def test_invalid_ai_recency_weight(self, tmp_path):
        """测试无效的时间衰减权重。"""
        env_file = tmp_path / ".env"
        env_file.write_text("AI_RECENCY_WEIGHT=invalid\n")

        config = Config(env_file=str(env_file))
        assert config.ai_recency_weight == 0.2  # 应该保持默认值

    def test_invalid_json_ai_models(self, tmp_path):
        """测试无效的 AI_MODELS JSON。"""
        env_file = tmp_path / ".env"
        env_file.write_text("AI_MODELS=invalid_json\n")

        config = Config(env_file=str(env_file))
        assert config.ai_models == []  # 应该保持默认值


class TestConfigBooleanParsing:
    """测试布尔值解析。"""

    def test_parse_boolean_true_values(self, tmp_path):
        """测试解析真值。"""
        for value in ("1", "true", "yes", "on"):
            env_file = tmp_path / ".env"
            env_file.write_text(f"AI_QUEUE_ENABLED={value}\n")
            config = Config(env_file=str(env_file))
            assert config.ai_queue_enabled is True

    def test_parse_boolean_false_values(self, tmp_path):
        """测试解析假值。"""
        env_file = tmp_path / ".env"
        env_file.write_text("AI_QUEUE_ENABLED=false\n")
        config = Config(env_file=str(env_file))
        assert config.ai_queue_enabled is False


class TestConfigEmptyHandling:
    """测试空值处理。"""

    def test_empty_env_var_not_override(self, monkeypatch):
        """测试空环境变量不覆盖配置。"""
        monkeypatch.setenv("AI_BASE_URL", "")

        config = Config(env_file="/nonexistent.env")
        assert config.ai_base_url is None

    def test_whitespace_handling(self, tmp_path):
        """测试空白字符处理。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "REDIS_HOST=  spaced-host.com  \n"
            "API_KEY=  sk-key  \n"
        )

        config = Config(env_file=str(env_file))
        assert config.redis_host == "spaced-host.com"
        assert config.api_key == "sk-key"

    def test_comment_lines_ignored(self, tmp_path):
        """测试注释行被忽略。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# This is a comment\n"
            "REDIS_HOST=real-host.com\n"
            "# Another comment\n"
        )

        config = Config(env_file=str(env_file))
        assert config.redis_host == "real-host.com"


class TestConfigProjectRoot:
    """测试项目根路径。"""

    def test_project_root_resolution(self):
        """测试项目根路径解析。"""
        config = Config(env_file="/nonexistent.env")
        assert config.project_root == PROJECT_ROOT
