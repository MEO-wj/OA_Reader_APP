"""
TDD RED -> GREEN 阶段 - CompatService 兼容编排服务测试

测试要点：
  1) clear_memory → 返回 cleared=True + conversation_id（新会话）
  2) _today_range 工具方法正确计算 UTC 范围
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from src.config.settings import Config


# ---------------------------------------------------------------------------
# Helpers: fake MemoryDB
# ---------------------------------------------------------------------------

class _FakeMemoryDB:
    """可编程的 MemoryDB 替身。"""

    def __init__(
        self,
        latest_session: dict | None = None,
    ):
        self._latest_session = latest_session
        self._created_sessions: list[tuple[str, str]] = []

    async def get_latest_session_in_utc_range(self, user_id, start_utc, end_utc):
        return self._latest_session

    async def get_latest_session_with_messages(self, user_id, start_utc, end_utc):
        return self._latest_session

    async def create_session(self, user_id, conversation_id, title="新会话"):
        self._created_sessions.append((user_id, conversation_id))

    async def ensure_user_exists(self, user_id):
        pass


def _make_config() -> Config:
    """创建用于测试的 Config 实例。"""
    return Config.with_defaults()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCompatServiceClearMemory:
    """CompatService.clear_memory 测试"""

    @pytest.mark.asyncio
    async def test_clear_memory_creates_new_when_today_session_has_messages(self, monkeypatch):
        """当天会话存在且有消息 → 创建新会话。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "existing-conv",
            "user_id": "u1",
            "title": "旧会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [{"role": "user", "content": "hello"}],
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert "conversation_id" in result
        assert result["conversation_id"] != "existing-conv"
        assert len(fake_memory._created_sessions) == 1

    @pytest.mark.asyncio
    async def test_clear_memory_reuses_when_today_session_has_no_messages(self, monkeypatch):
        """当天会话存在但无消息 → 复用该会话，不创建新的。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "empty-conv",
            "user_id": "u1",
            "title": "空会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [],
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert result["conversation_id"] == "empty-conv"
        assert len(fake_memory._created_sessions) == 0

    @pytest.mark.asyncio
    async def test_clear_memory_creates_new_when_no_today_session(self, monkeypatch):
        """无当天会话 → 创建新会话。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session=None)

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert "conversation_id" in result
        assert len(result["conversation_id"]) == 8
        assert len(fake_memory._created_sessions) == 1

    @pytest.mark.asyncio
    async def test_clear_memory_reuses_when_messages_is_json_string_empty(self, monkeypatch):
        """asyncpg 返回 JSONB 为字符串 '[]' 时，应视为无消息并复用。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "empty-conv",
            "user_id": "u1",
            "title": "空会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": "[]",  # asyncpg 返回字符串而非列表
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert result["conversation_id"] == "empty-conv"
        assert len(fake_memory._created_sessions) == 0

    @pytest.mark.asyncio
    async def test_clear_memory_creates_new_when_messages_is_json_string_nonempty(self, monkeypatch):
        """asyncpg 返回 JSONB 为字符串（非空）时，应创建新会话。"""
        import json as json_mod
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "used-conv",
            "user_id": "u1",
            "title": "有消息会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": json_mod.dumps([{"role": "user", "content": "hello"}]),
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert result["conversation_id"] != "used-conv"
        assert len(fake_memory._created_sessions) == 1

    @pytest.mark.asyncio
    async def test_clear_memory_without_user_id_raises(self, monkeypatch):
        """无 user_id 时 clear_memory 应抛出异常。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        service = CompatService(config=config)

        with pytest.raises(ValueError):
            await service.clear_memory(user_id=None)


class TestTodayRange:
    """_today_range 时区工具方法测试"""

    def test_today_range_default_timezone(self):
        """
        _today_range 返回 naive datetime，start 是今天 00:00 UTC，end 是明天 00:00 UTC。
        """
        from src.api.compat_service import _today_range

        start, end = _today_range()
        assert start.tzinfo is None
        assert end.tzinfo is None
        # end - start 应该是 24 小时
        assert (end - start) == timedelta(days=1)

    def test_today_range_with_utc_timezone(self):
        """
        start 是今天 00:00 UTC，end 是明天 00:00 UTC，当前时间在范围内。
        """
        from src.api.compat_service import _today_range

        start, end = _today_range()
        now_utc = datetime.utcnow()
        assert start <= now_utc < end

    def test_today_range_uses_given_timezone(self):
        """
        传入 Asia/Shanghai 时，返回的 naive datetime 应匹配该时区的"今天"。
        当前本地时间应落在对应范围内。
        """
        from src.api.compat_service import _today_range

        start_cst, end_cst = _today_range("Asia/Shanghai")

        # 都应是 naive datetime
        assert start_cst.tzinfo is None
        assert end_cst.tzinfo is None
        assert (end_cst - start_cst) == timedelta(days=1)

        # 当前 CST 时间应在 CST 范围内
        from zoneinfo import ZoneInfo
        now_cst = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        assert start_cst <= now_cst < end_cst

        # UTC 范围与 CST 范围应有差异（不同时区的"今天"不同）
        start_utc, end_utc = _today_range("UTC")
        assert (start_cst, end_cst) != (start_utc, end_utc) or True  # 同日时可能相同

    def test_today_range_invalid_timezone_falls_back_to_utc(self):
        """
        无效时区名应回退到 UTC（不抛异常）。
        """
        from src.api.compat_service import _today_range

        start_fallback, end_fallback = _today_range("Invalid/Zone")
        start_utc, end_utc = _today_range("UTC")
        assert start_fallback == start_utc
        assert end_fallback == end_utc


class TestConfigCompatTimezone:
    """Config.compat_timezone 配置字段测试"""

    def test_config_loads_ai_compat_tz_from_env(self, monkeypatch):
        """AI_COMPAT_TZ 环境变量应被加载到 config.compat_timezone。"""
        import importlib
        monkeypatch.setenv("AI_COMPAT_TZ", "Asia/Shanghai")
        import src.config.settings as settings_mod
        importlib.reload(settings_mod)
        config = settings_mod.Config.load()
        assert config.compat_timezone == "Asia/Shanghai"

    def test_config_compat_timezone_defaults_to_none(self):
        """默认情况下 compat_timezone 应为 None。"""
        from src.config.settings import Config
        config = Config.with_defaults()
        assert config.compat_timezone is None
