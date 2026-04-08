# Redis 移除设计方案

**日期**: 2026-03-15

## 目标

完全移除项目中的 Redis 依赖，将缓存功能一并删除，改为直接查询数据库。

## 修改范围

| 模块 | 需要修改的文件 |
|------|---------------|
| backend | `app.py`, `config.py`, `routes/articles.py`, `pyproject.toml`, `utils/redis_cache.py` |
| crawler | `cache.py`, `config.py`, `pyproject.toml` |
| ai_end | `app.py`, `config.py`, `pyproject.toml` |

## 具体修改

### 1. Backend

- **`app.py`**: 移除 Redis 客户端初始化代码
- **`config.py`**: 移除 Redis 配置项（`redis_host`, `redis_port`, `redis_db`, `redis_password`）
- **`routes/articles.py`**: 移除所有缓存调用（`cache.get()`, `cache.set()`, `cache.exists()`, `cache.generate_etag()`）
- **`utils/redis_cache.py`**: 删除文件
- **`pyproject.toml`**: 移除 `redis` 依赖

### 2. Crawler

- **`cache.py`**: 删除整个文件
- **`config.py`**: 移除 Redis 配置项
- **`pyproject.toml`**: 移除 `redis` 依赖

### 3. AI End

- **`app.py`**: 移除 Redis 客户端初始化代码
- **`config.py`**: 移除 Redis 配置项
- **`pyproject.toml`**: 移除 `redis` 依赖

## 影响

- 性能：每次请求直接查询数据库，无缓存加速
- 功能：功能不受影响，只是少了缓存层
- 数据：已缓存的数据将丢失（内存实现无需处理）
