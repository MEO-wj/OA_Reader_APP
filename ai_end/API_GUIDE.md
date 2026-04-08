# API 服务启动指南

## 访问地址

- API 文档: http://localhost:8000/docs
- 调试面板: http://localhost:8000/static/index.html
- 健康检查: http://localhost:8000/health

## 接口测试

```bash
# 健康检查
curl http://localhost:8000/health

# 技能列表
curl http://localhost:8000/skills

# 流式聊天
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "列出所有技能", "user_id": "test-user"}'
```

---

# API 接口完整文档

## 一、基础接口

### 1.1 健康检查

**GET** `/health`

返回服务状态和版本信息。

**响应示例:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### 1.2 技能列表

**GET** `/skills`

返回系统中所有可用的技能列表。

**响应示例:**
```json
{
  "skills": [
    {"name": "article-retrieval", "description": "OA 文章检索工具"}
  ],
  "data_source": "database",
  "skill_count": 1
}
```

---

## 二、聊天接口

### 2.1 流式聊天

**POST** `/chat`

SSE 流式聊天接口，支持实时流式输出。

**请求体:**
```json
{
  "message": "string",        // 聊天消息内容 (必需)
  "user_id": "string",        // 用户ID (必需, 1-64字符)
  "conversation_id": "string" // 会话ID (可选, 默认 "default")
}
```

**响应:** `Content-Type: text/event-stream`

```bash
# 示例
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "列出所有技能", "user_id": "user123"}'
```

### 2.2 获取聊天历史

**GET** `/chat/history`

获取指定用户的聊天历史记录。

**查询参数:**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户ID |
| conversation_id | string | 否 | 会话ID |

**响应:**
```json
{
  "user_id": "user123",
  "conversation_id": "abc123",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好，有什么可以帮助你的？"}
  ]
}
```

### 2.3 会话管理

#### 2.3.1 列出用户会话

**GET** `/chat/sessions`

列出用户所有会话。

**查询参数:**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户ID |

#### 2.3.2 创建新会话

**POST** `/chat/sessions`

创建新会话。

**请求体:**
```json
{
  "user_id": "string",  // 用户ID (必需)
  "title": "string"     // 会话标题 (可选)
}
```

#### 2.3.3 获取会话详情

**GET** `/chat/sessions/{conversation_id}`

获取指定会话详情。

**路径参数:**
- `conversation_id`: 会话ID

**查询参数:**
- `user_id`: 用户ID

#### 2.3.4 删除会话

**DELETE** `/chat/sessions/{conversation_id}`

删除指定会话。

### 2.4 用户管理

#### 2.4.1 列出最近用户

**GET** `/chat/users`

列出最近有聊天记录的用户。

**查询参数:**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 20 | 返回数量 |

#### 2.4.2 清空用户数据

**DELETE** `/chat/history`

清空指定用户的聊天历史与画像。

**查询参数:**
- `user_id`: 用户ID

---

## 2.5 兼容接口（旧 AI End 协议）

以下接口兼容旧 `ai_end` JSON 协议，backend 无需改代码即可通过 `AI_END_URL` 切换。

### 2.5.1 问答接口

**POST** `/ask`

兼容旧 `/ask` 接口，聚合事件流为单次 JSON 响应（`application/json`）。

**请求体:**
```json
{
  "question": "string",        // 必需，用户问题
  "top_k": 5,                  // 可选，建议返回的相关结果数（仅正整数有效）
  "display_name": "张三",       // 可选，用户称呼
  "user_id": "string"          // 可选，用户ID（传入时启用会话管理）
}
```

**响应（有 user_id 时）:**
```json
{
  "answer": "回答内容",
  "related_articles": [],
  "conversation_id": "a1b2c3d4",
  "session_created": true
}
```

**响应（无 user_id 时）:**
```json
{
  "answer": "回答内容",
  "related_articles": []
}
```

**错误响应（缺少 question）:**
```json
{"error": "请求参数错误，缺少question字段"}
```
HTTP 400

### 2.5.2 清除记忆

**POST** `/clear_memory`

新语义：不删除历史，创建新会话。

**请求体:**
```json
{
  "user_id": "string"          // 必需
}
```

**响应:**
```json
{
  "cleared": true,
  "conversation_id": "e5f6g7h8"
}
```

**错误响应（缺少 user_id）:**
```json
{"error": "用户信息缺失"}
```
HTTP 400

### 2.5.3 文本向量化

**POST** `/embed`

复用 embedding 能力，返回文本向量。

**请求体:**
```json
{
  "text": "string"             // 必需
}
```

**响应:**
```json
{
  "embedding": [0.1, 0.2, ...]
}
```

**错误响应（缺少 text）:**
```json
{"error": "请求参数错误，缺少text字段"}
```
HTTP 400

---

## 三、数据模型

### 3.1 Article（OA 文章）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| title | TEXT | 文章标题 |
| unit | TEXT | 发布单位 |
| link | TEXT | 原文链接（UNIQUE） |
| published_on | DATE | 发布日期 |
| content | TEXT | 文章完整内容 |
| summary | TEXT | 摘要 |
| attachments | JSONB | 附件列表 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

### 3.2 Vector（向量嵌入）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| article_id | BIGINT | 外键 → articles.id (CASCADE) |
| embedding | vector(1024) | 向量表示 |
| published_on | DATE | 发布日期 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

---

## 四、完整测试示例

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 获取技能列表
curl http://localhost:8000/skills

# 3. 流式聊天
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "列出所有技能", "user_id": "test-user"}'

# 4. 获取用户会话列表
curl "http://localhost:8000/chat/sessions?user_id=test-user"

# 5. 兼容接口 - 问答（单次 JSON）
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "最近有什么通知？", "user_id": "test-user"}'

# 6. 兼容接口 - 清除记忆（创建新会话）
curl -X POST http://localhost:8000/clear_memory \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user"}'

# 7. 兼容接口 - 文本向量化
curl -X POST http://localhost:8000/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "测试文本"}'
```

---

## 五、开发模式启动

```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

## Docker Compose 启动

```bash
# 启动 API 服务（数据库连接通过 .env 配置）
docker compose up --build
```

说明：

- API 服务通过 `.env` 文件连接外部 PostgreSQL (pgvector)，需确保 `.env` 中 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 配置正确。
- 如需自动迁移，可在 `.env` 中设置 `AUTO_MIGRATE=true`。
- 如需自动导入技能数据，可设置 `AUTO_IMPORT=true`。
