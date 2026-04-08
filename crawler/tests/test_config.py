"""Config 配置层单元测试。"""

from __future__ import annotations

import os
import pytest

from crawler.config import Config


class TestAiProviderMode:
    """ai_provider_mode 推断逻辑测试。"""

    def test_single_mode_when_no_primary_env(self, tmp_path):
        """未配置 AI_PRIMARY_* 时为 single 模式。"""
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=sk-test\nAI_BASE_URL=http://test\nAI_MODEL=gpt-4\n")
        config = Config(env_file=env_file)
        assert config.ai_provider_mode == "single"

    def test_fallback_mode_when_primary_and_fallback_configured(self, tmp_path):
        """配置了 AI_PRIMARY_* + AI_FALLBACK_* 时为 fallback 模式。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AI_PRIMARY_API_KEY=sk-primary\n"
            "AI_PRIMARY_BASE_URL=http://primary/v1/chat/completions\n"
            "AI_PRIMARY_MODEL=model-a\n"
            "AI_FALLBACK_API_KEY=sk-fallback\n"
            "AI_FALLBACK_BASE_URL=http://fallback/v1/chat/completions\n"
            "AI_FALLBACK_MODEL=model-b\n"
        )
        config = Config(env_file=env_file)
        assert config.ai_provider_mode == "fallback"
        assert config.ai_primary_api_key == "sk-primary"
        assert config.ai_primary_base_url == "http://primary/v1/chat/completions"
        assert config.ai_primary_model == "model-a"
        assert config.ai_fallback_api_key == "sk-fallback"
        assert config.ai_fallback_base_url == "http://fallback/v1/chat/completions"
        assert config.ai_fallback_model == "model-b"

    def test_env_override_takes_priority(self, tmp_path, monkeypatch):
        """环境变量覆盖 .env 文件的值。"""
        env_file = tmp_path / ".env"
        env_file.write_text("AI_PRIMARY_MODEL=old-model\n")
        monkeypatch.setenv("AI_PRIMARY_MODEL", "new-model")
        monkeypatch.setenv("AI_PRIMARY_API_KEY", "sk-key")
        monkeypatch.setenv("AI_PRIMARY_BASE_URL", "http://url")
        monkeypatch.setenv("AI_FALLBACK_API_KEY", "sk-fb")
        monkeypatch.setenv("AI_FALLBACK_BASE_URL", "http://fb-url")
        monkeypatch.setenv("AI_FALLBACK_MODEL", "fb-model")
        config = Config(env_file=env_file)
        assert config.ai_primary_model == "new-model"
        assert config.ai_provider_mode == "fallback"
