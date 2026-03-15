"""测试 routes/articles.py 不依赖缓存"""
import os

def test_articles_no_cache():
    """验证 articles 路由不依赖缓存"""
    articles_path = os.path.join(os.path.dirname(__file__), '..', 'routes', 'articles.py')
    with open(articles_path, 'r') as f:
        content = f.read()

    assert 'redis_cache' not in content, "articles.py 不应导入 redis_cache"
    assert 'get_cache' not in content, "articles.py 不应使用 get_cache"
    assert 'cache.get' not in content, "articles.py 不应使用 cache.get"
    assert 'cache.set' not in content, "articles.py 不应使用 cache.set"
    assert 'cache.exists' not in content, "articles.py 不应使用 cache.exists"
