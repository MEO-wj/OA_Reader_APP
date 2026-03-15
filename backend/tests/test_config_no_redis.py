"""测试 config.py 不依赖 Redis"""
import os

def test_config_no_redis():
    """验证配置中已移除 Redis 相关项"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.py')
    with open(config_path, 'r') as f:
        content = f.read()

    # 验证这些属性不存在
    assert 'redis_host' not in content, "config.py 不应包含 redis_host"
    assert 'redis_port' not in content, "config.py 不应包含 redis_port"
    assert 'redis_db' not in content, "config.py 不应包含 redis_db"
    assert 'redis_password' not in content, "config.py 不应包含 redis_password"
