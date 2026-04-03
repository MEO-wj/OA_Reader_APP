"""数据库连接模块测试

TDD RED 阶段：先编写测试，预期失败
TDD GREEN 阶段：使用 mock 通过测试
"""
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.core.db import get_pool, close_pool


@pytest_asyncio.fixture(autouse=True)
async def cleanup_pool():
    """每个测试后自动清理连接池"""
    yield
    # 重置模块级别的 _pool，避免测试间干扰
    import src.core.db
    src.core.db._pool = None
    src.core.db._pool_loop = None
    src.core.db._pool_lock = None
    src.core.db._pool_lock_loop = None


@pytest.mark.asyncio
@patch('src.core.db.asyncpg.create_pool', new_callable=AsyncMock)
async def test_get_pool(mock_create_pool):
    """测试获取连接池"""
    # 设置 mock 返回值 - 需要一个有 close 方法的 mock
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()
    mock_create_pool.return_value = mock_pool

    pool = await get_pool()
    assert pool is not None
    # 验证 create_pool 被调用
    mock_create_pool.assert_called_once()


@pytest.mark.asyncio
@patch('src.core.db.asyncpg.create_pool', new_callable=AsyncMock)
async def test_close_pool(mock_create_pool):
    """测试关闭连接池"""
    # 设置 mock 返回值
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()
    mock_create_pool.return_value = mock_pool

    await close_pool()
    # 再次获取应该创建新连接
    pool = await get_pool()
    assert pool is not None
    await close_pool()
    # 验证 close 被调用
    assert mock_pool.close.call_count >= 1


@pytest.mark.asyncio
async def test_get_pool_concurrent_init_only_once(monkeypatch):
    """并发获取连接池时只初始化一次"""
    from src.core import db as db_module

    db_module._pool = None

    created = {"count": 0}

    async def fake_create_pool(**kwargs):
        created["count"] += 1
        await asyncio.sleep(0.01)
        return object()

    monkeypatch.setattr("src.core.db.asyncpg.create_pool", fake_create_pool)

    await asyncio.gather(*(db_module.get_pool() for _ in range(10)))

    assert created["count"] == 1


@pytest.mark.asyncio
async def test_close_pool_handles_cross_loop_pool(monkeypatch):
    from src.core import db as db_module

    class FakePool:
        async def close(self):
            return None

    class FakeLoop:
        def is_running(self):
            return True

    db_module._pool = FakePool()
    db_module._pool_loop = FakeLoop()

    current_loop = object()
    monkeypatch.setattr("src.core.db.asyncio.get_running_loop", lambda: current_loop)

    called = {"count": 0}

    class FakeFuture:
        def result(self):
            called["count"] += 1
            return None

    def fake_run_coroutine_threadsafe(coro, loop):
        coro.close()
        return FakeFuture()

    monkeypatch.setattr("src.core.db.asyncio.run_coroutine_threadsafe", fake_run_coroutine_threadsafe)
    async def fake_to_thread(fn):
        return fn()

    monkeypatch.setattr("src.core.db.asyncio.to_thread", fake_to_thread)

    await db_module.close_pool()

    assert called["count"] == 1


@pytest.mark.asyncio
@patch("src.core.db.asyncpg.create_pool", new_callable=AsyncMock)
async def test_get_pool_recreates_when_loop_changed(mock_create_pool, monkeypatch):
    from src.core import db as db_module

    class OldLoop:
        def is_running(self):
            return False

    old_pool = object()
    new_pool = object()
    db_module._pool = old_pool
    db_module._pool_loop = OldLoop()
    mock_create_pool.return_value = new_pool

    monkeypatch.setattr("src.core.db.asyncio.get_running_loop", lambda: object())

    pool = await db_module.get_pool()

    assert pool is new_pool
    mock_create_pool.assert_called_once()
