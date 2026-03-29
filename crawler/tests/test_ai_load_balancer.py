"""PrimaryFallbackBalancer 单元测试。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from crawler.services.ai_load_balancer import ModelConfig, PrimaryFallbackBalancer


def _make_config(prefix: str = "primary") -> ModelConfig:
    return ModelConfig(
        api_key=f"sk-{prefix}-key",
        base_url=f"https://api.{prefix}.com/v1/chat/completions",
        model=f"{prefix}-model",
    )


class TestPrimaryFallbackBalancer:
    """主力/兜底负载均衡器测试。"""

    def test_get_model_returns_primary(self):
        balancer = PrimaryFallbackBalancer(
            primary=_make_config("primary"),
            fallback=_make_config("fallback"),
        )
        model = balancer.get_model()
        assert model.model == "primary-model"

    def test_get_fallback_returns_fallback(self):
        balancer = PrimaryFallbackBalancer(
            primary=_make_config("primary"),
            fallback=_make_config("fallback"),
        )
        model = balancer.get_fallback()
        assert model.model == "fallback-model"

    def test_mark_429_sets_cooldown(self):
        config = _make_config()
        balancer = PrimaryFallbackBalancer(
            primary=config,
            fallback=_make_config("fallback"),
        )
        assert config.is_available
        balancer.mark_429(config, cooldown_seconds=60)
        assert not config.is_available

    def test_mark_429_cooldown_expires(self):
        config = _make_config()
        balancer = PrimaryFallbackBalancer(
            primary=config,
            fallback=_make_config("fallback"),
        )
        balancer.mark_429(config, cooldown_seconds=60)
        assert not config.is_available
        # 模拟时间流逝
        with patch("crawler.services.ai_load_balancer.time") as mock_time:
            mock_time.time.return_value = time.time() + 61
            assert config.is_available


class TestModelConfig:
    """ModelConfig 保留行为测试。"""

    def test_default_available(self):
        config = _make_config()
        assert config.is_available

    def test_mark_429_makes_unavailable(self):
        config = _make_config()
        config.mark_429(cooldown_seconds=30)
        assert not config.is_available

    def test_mask_key_short(self):
        from crawler.services.ai_load_balancer import _mask_key
        assert _mask_key("short") == "***"

    def test_mask_key_long(self):
        from crawler.services.ai_load_balancer import _mask_key
        result = _mask_key("sk-abcdefgh12345678end")
        assert result.startswith("sk-abcde")
        assert result.endswith("8end")
