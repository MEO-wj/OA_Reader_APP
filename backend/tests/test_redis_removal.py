"""测试 app.py 不依赖 Redis"""
import pytest
import os

def test_app_no_redis_import():
    """验证 app.py 不导入 redis 模块"""
    app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    with open(app_path, 'r') as f:
        content = f.read()

    assert 'import redis' not in content, "app.py 不应导入 redis 模块"
    assert 'redis.Redis' not in content, "app.py 不应使用 redis.Redis"


def test_app_no_redis_cache_import():
    """验证 app.py 不导入 redis_cache"""
    app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    with open(app_path, 'r') as f:
        content = f.read()

    assert 'from backend.utils.redis_cache' not in content, "app.py 不应导入 redis_cache"
    assert 'redis_cache' not in content, "app.py 不应使用 redis_cache"


def test_app_no_redis_config():
    """验证 app.py 不引用 Redis 配置"""
    app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    with open(app_path, 'r') as f:
        content = f.read()

    assert 'redis_host' not in content, "app.py 不应引用 redis_host"
    assert 'redis_port' not in content, "app.py 不应引用 redis_port"
    assert 'redis_db' not in content, "app.py 不应引用 redis_db"
    assert 'redis_password' not in content, "app.py 不应引用 redis_password"


def test_app_no_storage_uri():
    """验证 app.py 不包含 Redis 相关的 storage_uri"""
    app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
    with open(app_path, 'r') as f:
        content = f.read()

    # 允许 memory:// 存储
    assert 'redis://' not in content, "app.py 不应包含 redis:// 存储URI"
    assert '_build_redis_storage_uri' not in content, "app.py 不应包含 _build_redis_storage_uri"
