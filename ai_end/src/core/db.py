"""数据库连接模块

提供异步 PostgreSQL 连接池管理
"""
import asyncio
import asyncpg
from src.config.settings import Config

_pool = None
_pool_lock = None
_pool_lock_loop = None
_pool_loop = None


def _get_pool_lock(current_loop):
    """返回绑定到当前事件循环的连接池互斥锁。"""
    global _pool_lock, _pool_lock_loop
    if _pool_lock is None or _pool_lock_loop is not current_loop:
        _pool_lock = asyncio.Lock()
        _pool_lock_loop = current_loop
    return _pool_lock


async def _recycle_stale_pool(current_loop):
    """当连接池绑定的事件循环与当前不一致时，安全回收旧连接池。"""
    global _pool, _pool_loop
    if not _pool:
        return

    if _pool_loop and _pool_loop is not current_loop and _pool_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_close_pool_internal(), _pool_loop)
        await asyncio.to_thread(future.result)
        return

    try:
        await _pool.close()
    except Exception:
        # 旧 loop 已失效时 close 可能抛错，直接重置引用避免复用坏连接池
        pass

    _pool = None
    _pool_loop = None


async def get_pool():
    """
    获取数据库连接池（单例模式）

    如果连接池不存在，则创建一个新的连接池。

    Returns:
        asyncpg.Pool: 数据库连接池

    Raises:
        asyncpg.PostgresError: 数据库连接错误时
    """
    global _pool, _pool_loop
    current_loop = asyncio.get_running_loop()
    async with _get_pool_lock(current_loop):
        if _pool is not None and _pool_loop is current_loop:
            return _pool

        if _pool is not None and _pool_loop is not current_loop:
            await _recycle_stale_pool(current_loop)

        if _pool is None:
            config = Config.load()
            db_host = getattr(config, 'db_host', None) or "localhost"
            db_port = getattr(config, 'db_port', None) or 5432
            db_user = getattr(config, 'db_user', None) or "ai_workflow"
            db_password = getattr(config, 'db_password', None) or "ai_workflow"
            db_name = getattr(config, 'db_name', None) or "ai_workflow"

            _pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name,
                min_size=2,
                max_size=20,
                command_timeout=60,
                max_queries=50000,
                max_inactive_connection_lifetime=300.0
            )
            _pool_loop = current_loop

        return _pool


async def _close_pool_internal():
    """在创建连接池的事件循环内关闭连接池。"""
    global _pool, _pool_loop
    if _pool:
        try:
            await _pool.close()
        except RuntimeError as exc:
            # 当底层事件循环已关闭时，close 可能抛 "Event loop is closed"；
            # 此时仅重置引用，避免继续复用坏连接池。
            if "Event loop is closed" not in str(exc):
                raise
        except Exception:
            # 兜底：关闭失败时仍重置引用，避免污染后续测试/请求。
            pass
    _pool = None
    _pool_loop = None


async def close_pool():
    """
    关闭数据库连接池

    安全地关闭现有连接池并将引用置为 None。
    """
    global _pool, _pool_loop
    if not _pool:
        _pool_loop = None
        return

    current_loop = asyncio.get_running_loop()
    if _pool_loop and _pool_loop is not current_loop and _pool_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_close_pool_internal(), _pool_loop)
        await asyncio.to_thread(future.result)
        return

    if _pool_loop and _pool_loop is not current_loop and _pool_loop.is_closed():
        # 池绑定的 loop 已关闭，无法在原 loop 安全 close，直接清理引用。
        _pool = None
        _pool_loop = None
        return

    await _close_pool_internal()
