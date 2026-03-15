# Redis 移除实现计划 (TDD)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完全移除项目中的 Redis 依赖，使用 TDD 确保功能正常

**Architecture:** 先写测试验证功能，再逐步移除 Redis 代码

**Tech Stack:** Python (backend, crawler, ai_end), Flask, pytest

---

## Task 1: 验证现有测试通过 (基线)

**Step 1: 运行 Backend 测试，确认当前状态**

```bash
cd backend && uv run pytest -v 2>&1 | head -50
```

**Step 2: 运行 AI End 测试**

```bash
cd ai_end && uv run pytest -v 2>&1 | head -50
```

**预期:** 测试通过或失败与 Redis 无关

---

## Task 2: Backend - 修改 app.py (TDD)

**Files:**
- Modify: `backend/app.py`

**Step 1: 写测试验证 app.py 无 Redis 依赖**

创建 `backend/tests/test_redis_removal.py`:

```python
"""测试 app.py 不依赖 Redis"""
import pytest
from unittest.mock import patch, MagicMock

def test_app_does_not_require_redis():
    """验证应用可以在没有 Redis 的情况下初始化"""
    with patch('redis.Redis') as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client

        # 重新导入 app 模块
        import importlib
        import backend.app as app_module
        importlib.reload(app_module)

        # 验证 redis 未被使用
        assert not hasattr(app_module, 'redis_client') or app_module.redis_client is None
```

**Step 2: 运行测试**

```bash
cd backend && uv run pytest tests/test_redis_removal.py -v
```

**Step 3: 修改 app.py 移除 Redis**

```python
# 移除这些代码:
# import redis
# redis_client = None
# if config.redis_host: ...
# storage_uri = ...
# from backend.utils.redis_cache import init_cache, RedisCache
# redis_cache = init_cache(redis_client)
```

**Step 4: 运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_redis_removal.py -v
```

---

## Task 3: Backend - 修改 config.py (TDD)

**Files:**
- Modify: `backend/config.py`

**Step 1: 写测试验证配置中无 Redis 项**

```python
def test_config_no_redis():
    """验证配置中已移除 Redis 相关项"""
    from backend.config import Config
    cfg = Config()

    # 验证这些属性不存在
    assert not hasattr(cfg, 'redis_host')
    assert not hasattr(cfg, 'redis_port')
    assert not hasattr(cfg, 'redis_db')
    assert not hasattr(cfg, 'redis_password')
```

**Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_config_no_redis.py -v
```

**预期:** FAIL (因为 Redis 配置项仍存在)

**Step 3: 修改 config.py 移除 Redis 配置**

移除 `redis_host`, `redis_port`, `redis_db`, `redis_password` 相关代码

**Step 4: 运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_config_no_redis.py -v
```

---

## Task 4: Backend - 修改 routes/articles.py (TDD)

**Files:**
- Modify: `backend/routes/articles.py`

**Step 1: 写测试验证缓存调用已移除**

```python
def test_articles_no_cache():
    """验证 articles 路由不依赖缓存"""
    import backend.routes.articles as articles_module

    # 读取源码检查
    source = articles_module.__file__
    with open(source) as f:
        content = f.read()

    assert 'redis_cache' not in content
    assert 'get_cache' not in content
    assert 'cache.get' not in content
    assert 'cache.set' not in content
```

**Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_articles_no_cache.py -v
```

**预期:** FAIL

**Step 3: 修改 articles.py 移除缓存调用**

- 移除 `from backend.utils.redis_cache import get_cache`
- 移除 `cache = get_cache()`
- 移除所有 `cache.` 调用

**Step 4: 运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_articles_no_cache.py -v
```

---

## Task 5: Backend - 删除 redis_cache.py

**Files:**
- Delete: `backend/utils/redis_cache.py`

**Step 1: 验证文件可安全删除**

```bash
ls backend/utils/redis_cache.py
```

**Step 2: 删除文件**

```bash
rm backend/utils/redis_cache.py
```

---

## Task 6: Backend - 修改 pyproject.toml

**Files:**
- Modify: `backend/pyproject.toml`

**Step 1: 移除 redis 依赖**

```toml
# 从 dependencies 中移除:
# "redis>=7.1.0",
```

---

## Task 7: Backend - 运行完整测试

**Step 1: 运行所有后端测试**

```bash
cd backend && uv run pytest -v
```

---

## Task 8: Crawler - 移除 Redis (类似流程)

**Files:**
- Delete: `crawler/cache.py`
- Modify: `crawler/config.py`
- Modify: `crawler/pyproject.toml`

**Step 1: 检查哪些代码引用了 cache.py**

```bash
grep -r "from crawler.cache import\|import crawler.cache" crawler/
```

**Step 2: 移除这些引用后删除 cache.py**

**Step 3: 移除 config.py 中的 Redis 配置**

**Step 4: 移除 pyproject.toml 中的 redis 依赖**

---

## Task 9: AI End - 移除 Redis (类似流程)

**Files:**
- Modify: `ai_end/app.py`
- Modify: `ai_end/config.py`
- Modify: `ai_end/pyproject.toml`

**Step 1: 写测试验证无 Redis 依赖**

**Step 2: 逐步移除 Redis 代码**

**Step 3: 运行测试验证**

---

## Task 10: 最终验证

**Step 1: 确认无 Redis 引用**

```bash
grep -r "redis\|Redis" --include="*.py" backend/ crawler/ ai_end/
```

**预期:** 无结果

**Step 2: 运行完整测试**

```bash
cd backend && uv run pytest -v
cd ai_end && uv run pytest -v
```

---

## Task 11: 提交代码

**Step 1: 添加并提交更改**

```bash
git add -A
git commit -m "refactor: 移除 Redis 依赖，使用数据库直连"
```
