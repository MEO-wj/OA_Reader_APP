"""
TDD RED 阶段 - 会话与时区能力扩展：MemoryDB 兼容测试

测试 get_latest_session_in_utc_range 方法：
  - 在给定 UTC 时间范围内返回最新创建的会话
  - 无匹配时返回 None
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from src.db.memory import MemoryDB

# Hardcoded test UUIDs (DB requires UUID type for user_id)
_UID_USER1 = "11111111-1111-1111-1111-111111111111"
_UID_USER42 = "42424242-4242-4242-4242-424242424242"


class TestGetLatestSessionInRange:
    """get_latest_session_in_utc_range 测试"""

    @pytest.mark.asyncio
    async def test_get_latest_session_in_range_returns_newest(self, monkeypatch):
        """
        RED #1: 在 UTC 范围内返回最新会话
        Given: 用户在指定范围内有多条会话，最新的是 c-latest
        When: 调用 get_latest_session_in_utc_range
        Then: 返回最新会话记录，conversation_id == "c-latest"
        """
        db = MemoryDB()

        # 构造 mock row（模拟 asyncpg Record）
        mock_row = {
            "user_id": _UID_USER1,
            "conversation_id": "c-latest",
            "title": "最新会话",
            "created_at": datetime(2025, 6, 1, 12, 0),
            "updated_at": datetime(2025, 6, 1, 12, 30),
        }

        conn = AsyncMock()
        conn.fetchrow.return_value = mock_row

        class _AcquireCtx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        pool = Mock()
        pool.acquire.return_value = _AcquireCtx()
        monkeypatch.setattr("src.db.memory.get_pool", AsyncMock(return_value=pool))

        start = datetime(2025, 6, 1, 0, 0)
        end = datetime(2025, 6, 2, 0, 0)
        result = await db.get_latest_session_in_utc_range(_UID_USER1, start, end)

        assert result is not None
        assert result["conversation_id"] == "c-latest"
        assert result["user_id"] == _UID_USER1
        # 验证 SQL 排序和参数
        sql = conn.fetchrow.call_args[0][0]
        assert "ORDER BY created_at DESC" in sql
        assert "LIMIT 1" in sql

    @pytest.mark.asyncio
    async def test_get_latest_session_in_range_returns_none_when_empty(self, monkeypatch):
        """
        RED #2: 范围内无会话时返回 None
        Given: 用户在指定范围内没有会话
        When: 调用 get_latest_session_in_utc_range
        Then: 返回 None
        """
        db = MemoryDB()

        conn = AsyncMock()
        conn.fetchrow.return_value = None

        class _AcquireCtx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        pool = Mock()
        pool.acquire.return_value = _AcquireCtx()
        monkeypatch.setattr("src.db.memory.get_pool", AsyncMock(return_value=pool))

        start = datetime(2025, 6, 1, 0, 0)
        end = datetime(2025, 6, 2, 0, 0)
        result = await db.get_latest_session_in_utc_range(_UID_USER1, start, end)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_session_in_range_passes_correct_params(self, monkeypatch):
        """
        RED #3: 验证传递给 SQL 的参数正确（user_id, start_utc, end_utc）
        Given: 调用 get_latest_session_in_utc_range
        When: 执行查询
        Then: fetchrow 被调用时参数顺序和值正确
        """
        db = MemoryDB()

        conn = AsyncMock()
        conn.fetchrow.return_value = None

        class _AcquireCtx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        pool = Mock()
        pool.acquire.return_value = _AcquireCtx()
        monkeypatch.setattr("src.db.memory.get_pool", AsyncMock(return_value=pool))

        start = datetime(2025, 1, 1, 0, 0)
        end = datetime(2025, 1, 2, 0, 0)
        await db.get_latest_session_in_utc_range(_UID_USER42, start, end)

        # fetchrow 的参数：(sql, user_id, start_utc, end_utc)
        call_args = conn.fetchrow.call_args[0]
        assert call_args[1] == _UID_USER42
        assert call_args[2] == start
        assert call_args[3] == end
