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
    {"name": "document-retrieval", "description": "通用文档检索工具"}
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

## 三、管理接口 (/api/admin)

### 3.1 模板接口（兼容保留）

#### 3.1.1 获取资料模板

**GET** `/api/admin/templates/{document_type}`

获取指定类型资料的模板定义。

**路径参数:**
- `document_type`: 仅支持 `documents`

**响应示例:**
```json
{
  "type": "documents",
  "description": "通用文档模板",
  "format": "markdown",
  "content": "# 文档标题\n\n文档内容..."
}
```

#### 3.1.2 下载示例文件

**GET** `/api/admin/templates/{document_type}/example`

下载指定类型资料的示例文件。

---

## 四、资料上传接口

### 4.1 上传文档

**POST** `/api/admin/documents`

上传文档。

**请求:**
- Content-Type: `multipart/form-data`
- 参数: `file` (`.md` 或 `.json` 文件)

**处理流程:**
1. 解析文件内容
2. 生成摘要
3. 生成向量 embedding
4. 存储到数据库

**响应:**
```json
{
  "status": "success",
  "message": "导入成功",
  "document": {
    "id": 1,
    "title": "document",
    "type": "markdown"
  },
  "processing_steps": [
    "读取文件内容",
    "生成摘要 (xxx 字符)",
    "生成向量 (1024维)",
    "存入数据库"
  ]
}
```

**示例:**
```bash
curl -X POST http://localhost:8000/api/admin/documents \
  -F "file=@document.md"
```

---

## 五、资料管理接口

### 5.1 获取文档列表

**GET** `/api/admin/documents`

获取文档列表。

**查询参数:**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 100 | 返回数量 (1-1000) |
| offset | int | 0 | 偏移量 |

**响应:**
```json
{
  "status": "success",
  "documents": [
    {
      "id": 1,
      "title": "文档标题",
      "summary": "摘要...",
      "source_type": "markdown",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 50,
  "limit": 100,
  "offset": 0
}
```

### 5.2 删除文档

**DELETE** `/api/admin/documents/{document_id}`

删除指定文档。

**路径参数:**
- `document_id`: 文档ID

**响应:**
```json
{
  "status": "success",
  "message": "删除成功"
}
```

---

## 六、数据模型

### 6.1 Document（通用文档）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| title | VARCHAR(500) | 文档标题 |
| content | TEXT | 文档完整内容 |
| summary | TEXT | 摘要 |
| source_type | VARCHAR(50) | 来源类型（markdown/json） |
| embedding | vector(1024) | 向量表示 |
| content_hash | VARCHAR(64) | 内容哈希 |
| metadata | JSONB | 扩展元数据 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

---

## 七、完整测试示例

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

# 5. 获取资料模板
curl http://localhost:8000/api/admin/templates/documents

# 6. 上传文档
curl -X POST http://localhost:8000/api/admin/documents \
  -F "file=@document.md"

# 7. 获取文档列表
curl "http://localhost:8000/api/admin/documents?limit=10&offset=0"

# 8. 删除文档
curl -X DELETE http://localhost:8000/api/admin/documents/1
```

---

## 八、开发模式启动

```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

## Docker Compose 启动

```bash
# 启动 PostgreSQL + API（镜像构建时已用 uv 安装依赖，运行时使用 uv run）
docker compose up --build

# 手动执行一次迁移（可选，通常用于手工修复）
docker compose --profile init run --rm migrate
```

说明：

- `api` 服务默认设置了 `AUTO_MIGRATE=true`，启动时会自动检测并执行增量迁移/结构对齐。
- 如不希望自动迁移，可在 compose 环境变量中将 `AUTO_MIGRATE` 设为 `false`。
- `AUTO_IMPORT` 在开发 compose 默认是 `false`，避免 `--reload` 场景重复触发高成本导入。
- 若将 `AUTO_IMPORT=true`，启动时会先做“缺失/变更探测”，仅当技能或文档数据集落后于本地文件时才执行导入。

## Docker 内一次性导入业务数据

> 注意：数据导入已迁移至通用文档处理框架，无需手动执行导入脚本。
