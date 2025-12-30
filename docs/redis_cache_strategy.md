# Redis 缓存策略设计文档

## 一、背景与问题分析

### 1.1 当前问题

| 问题 | 原因 | 影响 |
|------|------|------|
| **缓存是前几天的旧数据** | crawler 缓存的是 `articles:list:{date}:none`，但 APP 请求用的是 `since` 参数，键不匹配 | 缓存永远不命中，每次都查库 |
| **缓存键设计不匹配** | crawler 写 `articles:list:2025-01-15:none`，APP 可能请求 `articles:list:2025-01-15:1736899200` | 缓存利用率极低 |
| **没有按 ID 范围缓存** | 当前只按日期缓存，无法支持「加载更多」场景 | 需要新增功能 |
| **TTL 设置不一致** | crawler 用 3 天（259200 秒），backend 用 1 小时（3600 秒） | 行为不一致 |

### 1.2 需求目标

1. **首页数据缓存**：当天文章列表快速加载
2. **分页加载预缓存**：用户滑动加载更多时，下一页数据预先缓存到 Redis
3. **缓存命中率优化**：通过预缓存策略，让用户连续滑动时大部分请求命中缓存
4. **缓存一致性**：crawler 入库新文章后自动刷新缓存

---

## 二、缓存键设计

### 2.1 缓存键总览

| 缓存键格式 | 数据范围 | TTL | 说明 |
|-----------|----------|-----|------|
| `articles:today` | 当天所有文章列表 | 86400s（24小时） | 首页专用，crawler 覆盖刷新 |
| `articles:page:{before_date}:{before_id}:{limit}` | 以 {before_date, before_id} 为边界的一页文章 | 259200s（3天） | 分页加载用，**支持预缓存** |
| `articles:detail:{id}` | 单篇文章详情（含 content） | 259200s（3天） | 文章详情页用 |

**注意：**
- `articles:today`：crawler 每次入库会覆盖写入并重置 TTL，保持数据新鲜
- `articles:page:{before_date}:{before_id}:{limit}`：历史文章不会被修改，长 TTL 提高命中率
- **不保留** `articles:list:{date}:none` 旧缓存键

### 2.2 `articles:page:{before_date}:{before_id}:{limit}` 数据定义

**键值规则：**
- `{before_date}` 是**请求参数 `before_date` 的值**
- `{before_id}` 是**请求参数 `before_id` 的值**
- `{limit}` 是**请求参数 `limit` 的值**
- 内容：满足 `(published_on, id) < (before_date, before_id)` 的一页文章列表，按 `published_on DESC, id DESC` 排序
- 返回 `next_before_date` + `next_before_id` 用于下一次请求

**示例：**
```
请求: GET /api/articles?v=2&before_date=2025-01-15&before_id=81&limit=20
缓存键: articles:page:2025-01-15:81:20
返回: {
  "articles": [...],  ← 20 篇文章
  "next_before_date": "2025-01-15",
  "next_before_id": 61,             ← 下一页请求用这个值
  "has_more": true
}

下一页请求: GET /api/articles?v=2&before_date=2025-01-15&before_id=61&limit=20
缓存键: articles:page:2025-01-15:61:20
```

---

## 三、API 设计

### 3.1 获取当天所有文章（首页）

**请求：**
```
GET /api/articles/today
```

**说明：**
- 返回当天发布的所有文章（不支持 limit 参数，也无分页）
- `next_before_date` 返回当天日期，用于分页游标
- `next_before_id` 返回当天最小的文章 ID，用于加载更早日期的文章
- `has_more` 表示是否存在更早日期的文章
 - crawler 刷新 `articles:today` 时也会写入 `next_before_date` / `next_before_id` / `has_more`

**响应：**
```json
{
  "articles": [
    {
      "id": 100,
      "title": "文章标题",
      "unit": "发布单位",
      "link": "http://...",
      "published_on": "2025-01-15",
      "summary": "摘要内容",
      "created_at": "2025-01-15T10:30:00Z"
    }
    // ... 当天所有文章
  ],
  "next_before_date": "2025-01-15",
  "next_before_id": 81,
  "has_more": true
}
```

**缓存逻辑：**
```
1. 检查缓存键 "articles:today"
2. 命中则直接返回，带 ETag 支持 304
3. 未命中则查询数据库：WHERE published_on = TODAY ORDER BY published_on DESC, id DESC
4. 查询是否存在更早的文章：WHERE published_on < TODAY LIMIT 1
5. 写入 Redis，TTL=86400（24小时）
6. 返回数据
```

### 3.2 加载更旧的文章（分页）

**请求：**
```
GET /api/articles?v=2&before_date=2025-01-15&before_id=81&limit=20
```

**参数：**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| v | int | 否 | 1 | 接口版本，`1`=兼容旧分页，`2`=before_date + before_id |
| before_date | string | 是 | - | 游标日期（YYYY-MM-DD） |
| before_id | int | 是 | - | 游标 ID（同一天内继续向后翻页） |
| limit | int | 否 | 20 | 返回数量 |

**响应：**
```json
{
  "articles": [
    // 按 published_on DESC, id DESC 排序的一页文章
  ],
  "next_before_date": "2025-01-15",
  "next_before_id": 61,
  "has_more": true
}
```

**缓存逻辑：**
```
1. 检查缓存键 "articles:page:{before_date}:{before_id}:{limit}"  ← 使用请求参数
2. 命中则返回，带 ETag 支持 304
3. 未命中则：
   a. 查询数据库：WHERE (published_on < before_date) OR (published_on = before_date AND id < before_id)
      ORDER BY published_on DESC, id DESC LIMIT limit
   b. 写入当前页缓存 "articles:page:{before_date}:{before_id}:{limit}"，TTL=259200（3天）
   c. 异步预缓存下一页 "articles:page:{next_before_date}:{next_before_id}:{limit}"
   d. 返回数据
```

**到底判断：**
- `articles` 为空 → `has_more: false`, `next_before_date: null`, `next_before_id: null`
**兼容模式（v=1）**：
- 仅支持 `before_id`，按 `id DESC` 排序
- 缓存键使用 `articles:page:{before_id}:{limit}`

---

## 四、预缓存策略

### 4.1 核心思路

用户请求 `before_date=2025-01-15&before_id=60` 时，后端返回一页文章，同时**异步预缓存**下一页的文章到 Redis。这样用户下次请求时直接命中缓存。

### 4.2 预缓存流程

```
用户请求: GET /api/articles?v=2&before_date=2025-01-15&before_id=81&limit=20

┌─────────────────────────────────────────────────────────────┐
│ 1. 检查缓存                                                  │
│    cache_key = "articles:page:2025-01-15:81:20"  ← 用请求参数 │
│    cached = Redis.get(cache_key)                            │
│    if cached: return cached                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 未命中
┌─────────────────────────────────────────────────────────────┐
│ 2. 查询数据库                                                │
│    SELECT * FROM articles                                   │
│    WHERE (published_on < '2025-01-15')                       │
│       OR (published_on = '2025-01-15' AND id < 81)           │
│    ORDER BY published_on DESC, id DESC LIMIT 20              │
│                                                             │
│    返回: [80, 79, ..., 61]（共 20 篇）                       │
│    next_before_date = '2025-01-15'                           │
│    next_before_id = 61                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 写入当前页缓存（键 = 请求参数 before_date + before_id）  │
│    Redis.setex("articles:page:2025-01-15:81:20", 259200, {   │
│      articles: [80, ..., 61],                               │
│      next_before_date: '2025-01-15',                        │
│      next_before_id: 61,                                    │
│      has_more: true                                         │
│    })                                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 异步预缓存下一页（键 = 下一页的 before_date + before_id） │
│                                                             │
│    4.1 检查 "articles:page:2025-01-15:61:20" 是否已存在      │
│    4.2 若不存在，查询下一页:                                 │
│        SELECT * FROM articles                               │
│        WHERE (published_on < '2025-01-15')                   │
│           OR (published_on = '2025-01-15' AND id < 61)        │
│        ORDER BY published_on DESC, id DESC LIMIT 20          │
│    4.3 写入预缓存:                                          │
│        Redis.setex("articles:page:2025-01-15:61:20", 259200, {...}) │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. 返回当前页                                                │
│    return {                                                 │
│      articles: [80, ..., 61],                               │
│      next_before_date: '2025-01-15',                        │
│      next_before_id: 61,                                    │
│      has_more: true                                         │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 预缓存代码实现

```python
def _prefetch_next_page(before_date: str, before_id: int, limit: int):
    """异步预缓存下一页（线程安全版本）"""
    from flask import current_app

    def prefetch():
        # 使用独立的 Flask context，确保 DB/Redis 连接隔离
        with current_app.app_context():
            try:
                # 检查是否已缓存
                cache_key = f"articles:page:{before_date}:{before_id}:{limit}"
                if cache and cache.exists(cache_key):
                    return

                # 查询下一页（使用独立的 DB 连接）
                sql = """
                    SELECT id, title, unit, link, published_on, summary, created_at
                    FROM articles
                    WHERE (published_on < %s)
                       OR (published_on = %s AND id < %s)
                    ORDER BY published_on DESC, id DESC
                    LIMIT %s
                """
                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(sql, (before_date, before_date, before_id, limit))
                    articles = [_serialize_row(row) for row in cur.fetchall()]

                if not articles:
                    return

                # 写入预缓存
                next_before_date = articles[-1]['published_on']
                next_before_id = articles[-1]['id']
                result = {
                    "articles": articles,
                    "next_before_date": next_before_date,
                    "next_before_id": next_before_id,
                    "has_more": len(articles) == limit
                }
                cache.set(cache_key, result, expire_seconds=259200)  # 3天
            except Exception as e:
                logger.error(f"预缓存失败: {e}")

    thread = threading.Thread(target=prefetch, daemon=True)
    thread.start()
```

---

## 五、完整流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户操作流程                                    │
└─────────────────────────────────────────────────────────────────────────────┘

首次加载首页:
    APP/Web                       Backend                           Redis
      │                              │                                 │
      ├─ GET /api/articles/today ──→ │                                 │
      │                              ├─ 查当天所有文章                │
      │                              ├─ 查是否有更早文章             │
      │                              ├─ 写 articles:today (86400s)   │
      │                              └─ 返回当天所有 [100..81]       │
      │                              └────────────────────────────→  │
      │← 返回 + next_before_date=2025-01-15, next_before_id=81 ────┘     │

滑动到底部 (before_date=2025-01-15, before_id=81, limit=20):
    APP/Web                       Backend                           Redis
      │                              │                                 │
      ├─ GET ?v=2&before_date=2025-01-15&before_id=81&limit=20 ─→ │     │
      │                              ├─ 检查 articles:page:2025-01-15:81:20 │
      │                              │   (未命中)                     │
      │                              ├─ 查 [80..61]                  │
      │                              ├─ 写 articles:page:2025-01-15:81:20 (259200s) │
      │                              ├─ 异步预缓存 [60..41]          │
      │                              │   └→ articles:page:2025-01-15:61:20 │
      │                              └─ 返回 [80..61]               │
      │                              └────────────────────────────→  │
      │← 返回 + next_before_date=2025-01-15, next_before_id=61 ────┘     │

继续滑动 (before_date=2025-01-15, before_id=61, limit=20):
    APP/Web                       Backend                           Redis
      │                              │                                 │
      ├─ GET ?v=2&before_date=2025-01-15&before_id=61&limit=20 ─→ │     │
      │                              ├─ 检查 articles:page:2025-01-15:61:20 │
      │                              │   (命中! 已预缓存)            │
      │                              └─ 直接返回 [60..41]            │
      │← 返回 + next_before_date=2025-01-15, next_before_id=41 ────┘     │
```

---

## 六、Crawler 侧修改

### 6.1 刷新函数（crawler/cache.py）

```python
def refresh_today_cache(articles: list[dict], target_date: str) -> int:
    """刷新当天文章缓存（首页用）

    参数:
        articles: 当天所有文章列表
        target_date: 目标日期

    返回:
        成功写入返回 1，失败返回 0

    缓存键: articles:today
    TTL: 86400 秒（24 小时）- crawler 覆盖写入会重置 TTL
    """
    cfg = Config()
    if not cfg.redis_host:
        return 0

    client = _build_redis_client(cfg)

    # 写入 articles:today（所有当天文章）
    serialized = [_serialize_row(item) for item in articles]
    next_before_date = target_date if serialized else None
    next_before_id = serialized[-1]["id"] if serialized else None
    payload = {
        "articles": [{k: v for k, v in item.items() if k != "content"} for item in serialized],
        "next_before_date": next_before_date,
        "next_before_id": next_before_id,
        "has_more": False,  # crawler 无法判断是否有更早文章，由 backend 查询时确定
    }

    try:
        client.setex("articles:today", 86400, json.dumps(payload, ensure_ascii=False))
        logging.getLogger(__name__).info(
            "刷新 today 缓存成功",
            extra={"date": target_date, "count": len(articles)}
        )
        return 1
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "刷新 today 缓存失败: %s",
            exc,
            extra={"date": target_date}
        )
        return 0
```

### 6.2 修改入库逻辑（crawler/pipeline.py）

**移除旧的 list 缓存逻辑，只保留 today 缓存：**

```python
# 在入库成功后
if inserted > 0:
    cached_articles = self.repo.fetch_for_cache(conn, self.target_date)

    # 刷新 today 缓存（新逻辑）
    today_refreshed = refresh_today_cache(cached_articles, self.target_date)

    print(f"✅ 已刷新文章缓存: today={today_refreshed}")
```

---

## 七、实现文件清单

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `crawler/cache.py` | 新增 `refresh_today_cache()` 函数；**移除** `refresh_article_cache()` | P0 |
| `crawler/pipeline.py` | 调用 `refresh_today_cache()`；**移除** `refresh_article_cache()` 调用 | P0 |
| `backend/routes/articles.py` | 新增 `/today` 端点；**移除** `date/since` 参数；`before_date + before_id` 分页 + 预缓存 | P0 |
| `OAP-app/types/article.ts` | 新增 `PaginatedArticlesResponse` 类型 | P0 |
| `OAP-app/services/articles.ts` | 新增 `fetchTodayArticles()`, `fetchArticlesPage()` | P0 |
| `OAP-app/storage/article-storage.ts` | 新增分页状态存储 | P0 |
| `OAP-app/hooks/use-articles.ts` | 新增 `loadMoreArticles()` | P0 |
| `OAP-app/app/(tabs)/index.tsx` | 实现滑动到底部加载更多 | P0 |

---

## 八、缓存失效策略

| 操作 | 失效方式 | 说明 |
|------|----------|------|
| Crawler 入库新文章 | 写入 `articles:today`（覆盖） | 覆盖旧缓存，立即生效 |
| 用户手动刷新 | 依赖 304 机制 | 未变化则不传输数据 |
| TTL 到期 | 自动过期 | 无需手动处理 |

**不做主动删除**，依赖 TTL 和覆盖写入。

---

## 九、当前实现 vs 新方案对比

### 9.1 当前缓存实现分析

#### Crawler 侧（crawler/cache.py）

| 缓存键格式 | 数据内容 | TTL | 写入时机 |
|-----------|----------|-----|----------|
| `articles:list:{date}:none` | 当天文章列表（不含 content） | 3天（259200s） | 入库新文章后 |
| `articles:detail:{id}` | 单篇文章详情（含 content） | 3天（259200s） | 入库新文章后 |

**写入逻辑：**
```python
# crawler/cache.py:41-92 refresh_article_cache()
def refresh_article_cache(articles, target_date, days=3):
    # 1. 写入列表缓存
    list_key = f"articles:list:{target_date}:none"
    client.setex(list_key, ttl_seconds, json_payload)

    # 2. 批量写入详情缓存
    for article in articles:
        detail_key = f"articles:detail:{article_id}"
        client.setex(detail_key, ttl_seconds, article_json)
```

**清理逻辑：**
- `clear_article_list_cache()`: 删除 `articles:list:{target_date}:*`
- `clear_outdated_list_cache()`: 清理 3 天前的 `articles:list:*` 缓存

#### Backend 侧（backend/routes/articles.py）

| API 端点 | 缓存键格式 | TTL | 问题 |
|----------|-----------|-----|------|
| `GET /api/articles/` | `articles:list:{date}:{since}` | 3600s | **与 crawler 写入的键不匹配** |
| `GET /api/articles/<id>` | `articles:detail:{id}` | 3600s | 无问题 |
| `GET /api/articles/by-date/<date>` | `articles:by-date:{date}` | 3600s | 无问题 |

**当前查询逻辑（articles.py:48-190）：**
```python
# 1. 生成缓存键（基于 date 和 since 参数）
cache_key = f"articles:list:{date_str}:{since_str or 'none'}"

# 2. 尝试从缓存获取
cached_data = cache.get(cache_key)
if cached_data:
    # 生成 ETag，检查 If-None-Match
    return cached_data

# 3. 查询数据库
sql = "SELECT ... FROM articles WHERE published_on = %s"
if since_dt:
    sql += " AND created_at >= %s"

# 4. 写入缓存
cache.set(cache_key, response_data, expire_seconds=3600)
```

### 9.2 问题对比表

| 维度 | 当前实现 | 新方案 | 改进点 |
|------|----------|--------|--------|
| **缓存键匹配** | crawler 写 `articles:list:2025-01-15:none`<br>APP/Web 读 `articles:list:2025-01-15:1736899200` | 统一用 `articles:today` 和 `articles:page:{before_date}:{before_id}:{limit}` | 解决缓存永远不命中的问题 |
| **首页加载** | 无专用缓存，依赖 date/since 组合 | 专用 `articles:today` 键 | 首页请求稳定命中 |
| **分页加载** | 不支持 | `articles:page:{before_date}:{before_id}:{limit}` + 预缓存 | 支持滑动加载更多 |
| **TTL 一致性** | crawler 3天，backend 1小时 | 统一：today=24h, page=3d, detail=3d | 行为一致可预期 |
| **预缓存** | 无 | 返回当前页时异步缓存下一页 | 连续滑动时大部分命中缓存 |
| **到底判断** | 无 | 返回 `has_more` + `next_before_date` + `next_before_id` | APP 可判断是否继续加载 |
| **旧逻辑兼容** | - | **不保留** `articles:list:{date}:none` | 直接替换，API 不兼容旧版本 |

### 9.3 缓存键对比图

```
当前实现:
┌─────────────────────────────────────────────────────────────────┐
│ Crawler 写入                                                    │
│ articles:list:2025-01-15:none  ──────┐                         │
│ articles:detail:123                  │                         │
│ articles:detail:124                  │                         │
└──────────────────────────────────────┼─────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend/Web 读取（APP/Web 请求）                                │
│ articles:list:2025-01-15:1736899200  ✗ 不匹配！                 │
│ articles:list:2025-01-15:none          ○ 匹配（但很少用）        │
│ articles:detail:123                   ✓ 匹配                     │
└─────────────────────────────────────────────────────────────────┘

新方案（直接替换，不兼容旧版本）:
┌─────────────────────────────────────────────────────────────────┐
│ Crawler 写入                                                    │
│ articles:today                  ──────┐                         │
│ articles:detail:123                  │                         │
│ articles:detail:124                  │                         │
└──────────────────────────────────────┼─────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend/Web 读取（APP/Web 请求）                                │
│ articles:today                       ✓ 匹配！                   │
│ articles:page:2025-01-15:81:20       ✓ 新增（分页用）           │
│ articles:detail:123                  ✓ 匹配                     │
└─────────────────────────────────────────────────────────────────┘
```

### 9.4 迁移路径

**⚠️ 破坏性变更：直接替换旧 API**

**一次性替换策略：**

| 阶段 | 操作 | 说明 |
|------|------|------|
| 阶段 1 | Crawler 侧修改 | 新增 `refresh_today_cache()`，移除 `refresh_article_cache()` |
| 阶段 2 | Backend 侧修改 | 新增 `/today` 端点，`/api/articles/` 直接替换为 `before_date + before_id` 分页 |
| 阶段 3 | APP 侧修改 | 改用新 API，实现滚动加载 |
| 阶段 4 | Web 侧修改 | 与 APP 使用相同 API |

**注意事项：**
- 旧版本 APP/Web 将无法正常使用
- 建议在维护窗口期执行，或先在测试环境验证
- 无需保留旧缓存，`articles:list:*` 会自然过期

---

## 十、API 端点对比

### 10.1 当前 API 端点（将被移除）

| 端点 | 参数 | 缓存键 | 问题 |
|------|------|--------|------|
| `GET /api/articles/` | `date`, `since` | `articles:list:{date}:{since}` | 与 crawler 写入的键不匹配 |
| `GET /api/articles/<id>` | - | `articles:detail:{id}` | 无问题 |
| `GET /api/articles/by-date/<date>` | - | `articles:by-date:{date}` | 无问题 |

### 10.2 新 API 端点

| 端点 | 参数 | 缓存键 | TTL | 说明 |
|------|------|--------|-----|------|
| `GET /api/articles/today` | - | `articles:today` | 24h | 获取当天所有文章 |
| `GET /api/articles/` | `v`(可选), `before_date` (v2 必填), `before_id` (必填), `limit` (可选) | `articles:page:{before_date}:{before_id}:{limit}` | 3天 | 分页加载更旧文章 |
| `GET /api/articles/<id>` | - | `articles:detail:{id}` | 3天 | 获取文章详情 |

### 10.3 Web 端实现

Web 端使用与 APP 端相同的 API：
- 首页：`GET /api/articles/today`
- 滚动加载：`GET /api/articles/?v=2&before_date=YYYY-MM-DD&before_id=xxx&limit=20`
- ETag/304 支持：Web 端可以使用浏览器缓存机制

---

## 十一、设计修正与澄清

### 11.1 分页缓存键设计（重要修正）

**原设计问题：**
```
请求: before_date=2025-01-15, before_id=81, limit=20
读取: articles:page:2025-01-15:81:20  ❌
写入: articles:page:2025-01-15:61:20  ❌ (返回最后一条 id=61)
→ 读写键不一致，永远 miss
```

**修正后的设计：**

缓存键**始终使用请求参数 `before_date` + `before_id` + `limit`**，而非返回数据的 `next_before_id`：

```
请求: GET /api/articles?v=2&before_date=2025-01-15&before_id=81&limit=20

缓存键: articles:page:2025-01-15:81:20  (使用请求参数 before_date + before_id + limit)

返回:
{
  "articles": [...],
  "next_before_date": "2025-01-15",
  "next_before_id": 61,  ← 用于下一次请求的 before_id
  "has_more": true
}

下一次请求: GET /api/articles?v=2&before_date=2025-01-15&before_id=61&limit=20
缓存键: articles:page:2025-01-15:61:20
```

**修正后的流程：**
```
┌─────────────────────────────────────────────────────────────┐
│ 1. 检查缓存                                                  │
│    cache_key = "articles:page:{before_date}:{before_id}:{limit}"  ← 用请求参数 │
│    cached = Redis.get(cache_key)                            │
│    if cached: return cached                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 未命中
┌─────────────────────────────────────────────────────────────┐
│ 2. 查询数据库                                                │
│    SELECT * FROM articles                                   │
│    WHERE (published_on < '2025-01-15')                       │
│       OR (published_on = '2025-01-15' AND id < 81)           │
│    ORDER BY published_on DESC, id DESC LIMIT 20              │
│                                                             │
│    返回: [...], next_before_id = 61                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 写入当前页缓存（键 = 请求参数）                           │
│    Redis.setex("articles:page:2025-01-15:81:20", 7200, {     │
│      articles: [...],                                       │
│      next_before_date: "2025-01-15",                         │
│      next_before_id: 61,                                    │
│      has_more: true                                         │
│    })                                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 异步预缓存下一页（键 = 下一页的 before_date + before_id） │
│                                                             │
│    4.1 下一页的 before_id = 61                               │
│    4.2 检查 "articles:page:2025-01-15:61:20" 是否已存在       │
│    4.3 若不存在，查询并写入:                                 │
│        Redis.setex("articles:page:2025-01-15:61:20", 7200, {...}) │
└─────────────────────────────────────────────────────────────┘
```

### 11.2 预缓存线程安全（修正）

**问题：**
直接使用 `threading.Thread` 在 Flask 生产环境会导致：
1. 数据库连接复用问题（`db_session()` 可能跨线程共享）
2. Redis 连接非线程安全
3. 线程堆积风险

**修正方案：**

```python
def _prefetch_next_page(before_date: str, before_id: int, limit: int):
    """异步预缓存下一页（线程安全版本）"""
    from flask import current_app

    def prefetch():
        # 使用独立的 Flask context，确保 DB/Redis 连接隔离
        with current_app.app_context():
            try:
                # 检查是否已缓存
                cache_key = f"articles:page:{before_date}:{before_id}:{limit}"
                if cache and cache.exists(cache_key):
                    return

                # 查询下一页（使用独立的 DB 连接）
                sql = """
                    SELECT id, title, unit, link, published_on, summary, created_at
                    FROM articles
                    WHERE (published_on < %s)
                       OR (published_on = %s AND id < %s)
                    ORDER BY published_on DESC, id DESC
                    LIMIT %s
                """
                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(sql, (before_date, before_date, before_id, limit))
                    articles = [_serialize_row(row) for row in cur.fetchall()]

                if not articles:
                    return

                # 写入预缓存（使用独立的 Redis 连接）
                next_before_date = articles[-1]['published_on']
                oldest_id = articles[-1]['id']
                result = {
                    "articles": articles,
                    "next_before_date": next_before_date,
                    "next_before_id": oldest_id,
                    "has_more": len(articles) == limit
                }
                cache.set(cache_key, result, expire_seconds=259200)  # 3天
            except Exception as e:
                logger.error(f"预缓存失败: {e}")

    thread = threading.Thread(target=prefetch, daemon=True)
    thread.start()
```

**生产环境推荐方案：**
- 使用 Celery 或 RQ 等后台任务队列
- 或使用异步框架（如 FastAPI + asyncio）

### 11.3 ETag 生成规则（补充）

**ETag 计算方式：**
```python
import hashlib
import json

def generate_etag(data: dict) -> str:
    """基于 JSON 内容生成 ETag

    规则：
    1. 将数据序列化为 JSON（sort_keys=True 确保顺序一致）
    2. 计算 MD5 哈希值
    3. 返回 32 位十六进制字符串
    """
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode('utf-8')).hexdigest()
```

**304 响应触发条件：**
```python
etag = generate_etag(response_data)

# 检查客户端的 If-None-Match 头
if request.headers.get('If-None-Match') == etag:
    return make_response('', 304)

# 设置 ETag 响应头
response.headers['ETag'] = etag
```

**注意事项：**
1. **首页缓存**：`articles:today` 的 ETag 会随 crawler 写入而变化，客户端需能处理 ETag 失效
2. **分页缓存**：`articles:page:{before_date}:{before_id}:{limit}` 内容相对稳定，ETag 有效期较长
3. ** crawler 覆盖写入**：crawler 入库新文章时会覆盖 `articles:today`，导致 ETag 变化，这是预期行为

### 11.4 旧缓存清理策略（简化版）

**由于直接替换旧 API，无需分阶段迁移。**

**清理命令：**
```python
# 清理所有旧的 list 缓存（可选，等待自然过期也可）
cache.clear_pattern("articles:list:*")
```

**说明：**
- 旧的 `articles:list:{date}:none` 缓存会随 TTL 自然过期
- Crawler 不再写入旧缓存键
- Backend 不再读取旧缓存键
- 无需主动清理，等待 3 天自然过期即可

---

## 十二、监控与调优

### 10.1 缓存命中率监控

```python
# 在 backend/utils/redis_cache.py 中添加

class RedisCache:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.enabled = redis_client is not None
        self.hits = 0
        self.misses = 0

    def get(self, key: str, default=None):
        if not self.enabled:
            return default

        value = self.redis_client.get(key)
        if value is None:
            self.misses += 1
            return default

        self.hits += 1
        # ... 反序列化逻辑

    def get_stats(self):
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.2%}"
        }
```

### 10.2 预缓存效果评估

| 指标 | 目标值 |
|------|--------|
| 首页缓存命中率 | > 90% |
| 分页缓存命中率（连续滑动） | > 80% |
| 预缓存覆盖率 | > 70% |

---

## 十一、附录：缓存键命名规范

| 前缀 | 用途 | 示例 |
|------|------|------|
| `articles:today` | 当天文章列表 | `articles:today` |
| `articles:page:` | 分页数据 | `articles:page:2025-01-15:81:20` |
| `articles:detail:` | 文章详情 | `articles:detail:123` |

**已废弃（不使用）：**
- `articles:list:{date}:none` - 旧版缓存键，已弃用
