# OAP 后端 API 文档（当前实现）

## 概述

本文档描述 **当前已实现** 的后端 API 与行为约定，并标注已弃用/未实现部分。
当前能力包含：账号密码登录（含校园认证校验）、文章查询（支持分页）、向量问答。

## 技术栈

- **框架**: Flask 3.0.0+
- **数据库**: PostgreSQL（支持 pgvector）
- **缓存**: Redis
- **认证**: JWT
- **限流**: Flask-Limiter（默认：100/day, 20/hour）
- **CORS**: Flask-CORS

## 基本信息

### 基础 URL

生产环境：`oap-backend.handywote.top/api`（协议以部署为准）
开发环境：`http://localhost:4420/api`

### 认证

- `POST /auth/token`：用户名/密码登录（后端进行校园认证校验）
- `POST /auth/token/refresh`：刷新 JWT
- `POST /auth/logout`：登出（刷新令牌失效）
- `GET /auth/me`：获取当前用户信息
- 请求头：`Authorization: Bearer <access_token>`
- 说明：文章接口当前未强制鉴权；AI 接口要求鉴权

### 缓存策略

**缓存键设计**：
- `articles:today` - 当天所有文章，TTL 24h
- `articles:page:{before_date}:{before_id}:{limit}` - 分页文章，TTL 3天
- `articles:detail:{id}` - 文章详情，TTL 3天

**ETag/304 支持**：
- 所有文章接口支持 ETag，客户端使用 `If-None-Match` 获取 304
- 缓存控制头：`Cache-Control: max-age=3600, public`

### 响应格式

错误响应：

```json
{
  "error": "错误描述"
}
```

成功响应：按端点返回业务字段（不额外包裹 `status`）。

## API 端点

### 1. 认证模块

#### 1.1 用户名/密码登录

```
POST /auth/token
```

**请求体**:

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**响应**:

```json
{
  "access_token": "jwt_access",
  "refresh_token": "jwt_refresh",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "username": "username",
    "display_name": "用户名称",
    "roles": []
  }
}
```

#### 1.2 刷新访问令牌

```
POST /auth/token/refresh
```

**请求体**:

```json
{
  "refresh_token": "jwt_refresh"
}
```

**响应**:

```json
{
  "access_token": "jwt_access",
  "refresh_token": "jwt_refresh",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "username": "username",
    "display_name": "用户名称",
    "roles": []
  }
}
```

#### 1.3 登出

```
POST /auth/logout
```

**请求体**:

```json
{
  "refresh_token": "jwt_refresh"
}
```

**响应**:

```json
{
  "message": "已登出"
}
```

#### 1.4 获取当前用户信息

```
GET /auth/me
```

**响应**:

```json
{
  "user_id": "uuid",
  "display_name": "用户名称",
  "roles": []
}
```

### 2. 文章模块

#### 2.1 获取当天所有文章

```
GET /articles/today
```

**响应**:

```json
{
  "articles": [
    {
      "id": 1,
      "title": "文章标题",
      "unit": "发布单位",
      "link": "文章链接",
      "published_on": "2023-06-15",
      "summary": "文章摘要",
      "attachments": [
        {
          "name": "附件名称",
          "url": "附件链接"
        }
      ],
      "created_at": "2023-06-15T10:00:00"
    }
    // ... 当天所有文章
  ],
  "next_before_date": "2023-06-15",
  "next_before_id": 81,
  "has_more": true
}
```

**说明**：
- 返回当天发布的所有文章（无分页）
- `next_before_date`：下一页游标日期；若当天无文章，则为最近发布日期
- `next_before_id`：该游标日期下的最大 ID，用于继续加载更早文章
- `has_more`：是否存在更早日期的文章
- 支持 ETag/304 缓存
- 缓存键：`articles:today`，TTL 24h

#### 2.2 分页加载更旧的文章

```
GET /articles?v=2&before_date=2023-06-15&before_id=81&limit=20
```

**查询参数**:
- `v`（可选）：接口版本，`1`=仅 before_id（兼容模式），`2`=before_date + before_id（新逻辑）
- `before_date`（v=2 必填）：游标日期，格式 `YYYY-MM-DD`
- `before_id`（必填）：游标 ID，用于同一天内继续向后翻页
- `limit`（可选）：返回数量，默认 20，最大 100

**响应**:

```json
{
  "articles": [
    {
      "id": 80,
      "title": "文章标题",
      "unit": "发布单位",
      "link": "文章链接",
      "published_on": "2023-06-15",
      "summary": "文章摘要",
      "attachments": [],
      "created_at": "2023-06-15T10:00:00"
    }
    // ... ID 范围 [61, 80] 的文章
  ],
  "next_before_date": "2023-06-15",
  "next_before_id": 61,
  "has_more": true
}
```

**说明**：
- 返回满足 `(published_on, id) < (before_date, before_id)` 的文章
- 排序规则：`published_on DESC, id DESC`
- 支持预缓存策略：返回当前页时异步缓存下一页
- 支持 ETag/304 缓存
- 缓存键：`articles:page:{before_date}:{before_id}:{limit}`，TTL 3天
- `has_more` 为 false 时表示已到最早文章
 - 兼容模式：`v=1` 仅支持 `before_id`，按 `id DESC` 排序（计划弃用）

**错误响应**:
- 400：`v=2` 缺少 `before_date` 或 `before_id` 参数

#### 2.3 获取文章详情

```
GET /articles/{article_id}
```

**响应**:

```json
{
  "id": 1,
  "title": "文章标题",
  "unit": "发布单位",
  "link": "文章链接",
  "published_on": "2023-06-15",
  "content": "文章内容",
  "summary": "文章摘要",
  "attachments": [],
  "created_at": "2023-06-15T10:00:00",
  "updated_at": "2023-06-15T10:00:00"
}
```

**说明**：
- 支持 ETag/304 缓存
- 缓存键：`articles:detail:{id}`，TTL 3天

### 3. AI 问答模块

#### 3.1 官方模式问答（按配置限制向量范围）

```
POST /ai/ask
```

**请求体**:

```json
{
  "question": "你的问题",
  "top_k": 3
}
```

**响应**:

```json
{
  "answer": "AI生成的回答",
  "related_articles": [
    {
      "id": 1,
      "title": "相关文章标题",
      "unit": "发布单位",
      "published_on": "2023-06-15",
      "similarity": 0.95,
      "content_snippet": "正文片段",
      "summary_snippet": "摘要片段"
    }
  ]
}
```

#### 3.2 生成向量嵌入

```
POST /ai/embed
```

**请求体**:

```json
{
  "text": "要生成嵌入的文本"
}
```

**响应**:

```json
{
  "embedding": []
}
```

## 缓存策略详解

### 缓存键总览

| 缓存键格式 | 数据范围 | TTL | 说明 |
|-----------|----------|-----|------|
| `articles:today` | 当天所有文章列表 | 86400s（24小时） | 首页专用，crawler 覆盖刷新 |
| `articles:page:{before_date}:{before_id}:{limit}` | 以 {before_date, before_id} 为边界的一页文章 | 259200s（3天） | 分页加载用，支持预缓存 |
| `articles:detail:{id}` | 单篇文章详情（含 content） | 259200s（3天） | 文章详情页用 |

### 预缓存策略

当用户请求分页数据时（如 `before_date=2023-06-15, before_id=81, limit=20`），后端会：
1. 返回排序后的一页文章
2. 异步预缓存下一页（使用返回的 `next_before_date` + `next_before_id`）
3. 用户继续滑动时直接命中缓存

### Crawler 刷新逻辑

- **`articles:today`**：crawler 每次入库会覆盖写入并重置 TTL，保持数据新鲜
- **`articles:detail:{id}`**：crawler 入库新文章时写入详情缓存
- **`articles:page:*`**：由后端按需写入，crawler 不操作

## 已完成 / 已弃用 / 未实现

### 已完成
- 认证：`/auth/token`、`/auth/token/refresh`、`/auth/logout`、`/auth/me`
- 文章：`/articles/today`、`/articles/`（分页）、`/articles/<id>`
- AI：`/ai/ask`、`/ai/embed`
- 缓存：ETag 支持，三层缓存策略，预缓存

### 已弃用（不再实现）
- SSO token 换 JWT（原 `/auth/login`）
- 代理模式问答（`/ai/ask/proxy`）
- 阅读状态同步（`/articles/read`）
- 通知测试（`/notifications/test`）
- 旧版文章接口：`/articles?date=&since=`、`/articles/by-date/<date>`

## 错误码

| 状态码 | 描述 |
|--------|------|
| 200 | 成功 |
| 304 | 资源未修改 |
| 400 | 请求参数错误 |
| 401 | 未授权访问 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

## 部署与配置

### 环境变量

**核心配置**：
- `DATABASE_URL`
- `AUTH_JWT_SECRET`
- `AUTH_REFRESH_HASH_KEY`

**AI/Embedding（AI 问答使用）**：
- `AI_BASE_URL`
- `AI_MODEL`
- `API_KEY`
- `EMBED_BASE_URL`
- `EMBED_MODEL`
- `EMBED_API_KEY`
- `EMBED_DIM`（默认 1024）

**可选**：
- `REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`/`REDIS_PASSWORD`
- `AI_VECTOR_LIMIT_DAYS`
- `AI_VECTOR_LIMIT_COUNT`

### 依赖安装（后端）

```bash
uv sync
```

### 启动服务

以实际后端入口为准，`backend/app.py` 默认端口为 4420。

## 开发与测试

### 运行测试

```bash
uv run pytest
```

### 代码风格检查

```bash
uv run ruff check .
```
