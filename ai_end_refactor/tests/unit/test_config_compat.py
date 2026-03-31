"""
TDD RED 阶段 - 会话与时区能力扩展：配置兼容测试

测试 ai_compat_timezone 配置项的读取优先级：
  AI_COMPAT_TZ > AI_COMPAT_TIMEZONE > None
"""
import pytest
from src.config.settings import Config


class TestCompatTimezone:
    """时区配置读取优先级测试"""

    def test_resolve_compat_timezone_prefers_env(self, monkeypatch):
        """
        RED #1: AI_COMPAT_TZ 环境变量优先读取
        Given: 设置了 AI_COMPAT_TZ 环境变量
        When: 调用 Config.load()
        Then: ai_compat_timezone 等于 AI_COMPAT_TZ 的值
        """
        monkeypatch.setenv("AI_COMPAT_TZ", "Asia/Shanghai")
        monkeypatch.delenv("AI_COMPAT_TIMEZONE", raising=False)

        cfg = Config.load()
        assert cfg.ai_compat_timezone == "Asia/Shanghai"

    def test_resolve_compat_timezone_fallback_to_long_name(self, monkeypatch):
        """
        RED #2: AI_COMPAT_TZ 未设置时回退到 AI_COMPAT_TIMEZONE
        Given: 未设置 AI_COMPAT_TZ，设置了 AI_COMPAT_TIMEZONE
        When: 调用 Config.load()
        Then: ai_compat_timezone 等于 AI_COMPAT_TIMEZONE 的值
        """
        monkeypatch.delenv("AI_COMPAT_TZ", raising=False)
        monkeypatch.setenv("AI_COMPAT_TIMEZONE", "UTC")

        cfg = Config.load()
        assert cfg.ai_compat_timezone == "UTC"

    def test_resolve_compat_timezone_tz_takes_priority(self, monkeypatch):
        """
        RED #3: 同时设置 AI_COMPAT_TZ 和 AI_COMPAT_TIMEZONE 时，AI_COMPAT_TZ 优先
        Given: 同时设置了两个环境变量
        When: 调用 Config.load()
        Then: ai_compat_timezone 使用 AI_COMPAT_TZ 的值
        """
        monkeypatch.setenv("AI_COMPAT_TZ", "Asia/Tokyo")
        monkeypatch.setenv("AI_COMPAT_TIMEZONE", "America/New_York")

        cfg = Config.load()
        assert cfg.ai_compat_timezone == "Asia/Tokyo"

    def test_resolve_compat_timezone_defaults_to_none(self, monkeypatch):
        """
        RED #4: 未设置任何时区环境变量时，默认为 None
        Given: 两个环境变量都未设置
        When: 调用 Config.load()
        Then: ai_compat_timezone 为 None
        """
        monkeypatch.delenv("AI_COMPAT_TZ", raising=False)
        monkeypatch.delenv("AI_COMPAT_TIMEZONE", raising=False)

        cfg = Config.load()
        assert cfg.ai_compat_timezone is None

    def test_with_defaults_compat_timezone_is_none(self):
        """
        RED #5: with_defaults() 创建的配置中 ai_compat_timezone 为 None
        Given: 使用 Config.with_defaults()
        When: 访问 ai_compat_timezone
        Then: 值为 None
        """
        cfg = Config.with_defaults()
        assert cfg.ai_compat_timezone is None
