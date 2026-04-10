# OAP（智能校园OA助手）项目架构文档

> 版本：1.0 | 更新日期：2026-03-27

---

## 📋 目录

- [项目概览](#项目概览)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [接口通讯](#接口通讯)
- [数据模型](#数据模型)
- [数据流转](#数据流转)
- [关键技术实现](#关键技术实现)
- [缓存策略](#缓存策略)
- [部署架构](#部署架构)

---

## 项目概览

OAP 是一款为学校OA系统打造的智能移动助手，提供 **AI摘要**、**智能搜索** 和 **推送通知** 三大核心功能。

### 技术栈总览

| 模块 | 技术栈 | 端口 | 职责 |
|------|--------|------|------|
| **OAP-app** | React Native + Expo 54 + TypeScript | - | 多端客户端 (iOS/Android/Web) |
| **backend** | Go + Gin + GORM + PostgreSQL | 4420 | API 服务、认证、文章查询 |
| **ai_end** | Python + FastAPI + 技能系统 | 4421 | AI 服务、RAG 问答、技能调用、SSE 流式响应 |
| **crawler** | Python + psycopg + requests | - | 数据爬取、AI 摘要、向量生成 |

### 核心特性

- 🤖 **智能摘要**：AI 自动提炼文章核心内容
- 🔍 **语义搜索**：基于向量相似度的自然语言问答
- 📱 **多端适配**：一套代码，iOS/Android/Web 通用
- 🔐 **校园认证**：集成校园 CAS SSO 系统

---

## 系统架构

### 整体架构图

```mermaid
flowchart TB
    subgraph 用户层["👤 用户层"]
        iOS[iOS App]
        Android[Android App]
        Web[Web App]
    end

    subgraph 网关层["🚪 API 网关"]
        Backend["Backend (Go:4420)<br/>认证 / 文章 / AI代理"]
    end

    subgraph 服务层["⚙️ 服务层"]
        AIEnd["AI_end (FastAPI:4421)<br/>技能系统 / 向量搜索"]
        Crawler["Crawler (Python)<br/>爬虫管道"]
    end

    subgraph 数据层["💾 数据层"]
        PG[("PostgreSQL<br/>+ pgvector")]
    end

    subgraph 外部系统["🌐 外部系统"]
        OA["OA 系统<br/>oa.stu.edu.cn"]
        LLM["LLM API<br/>(OpenAI 兼容)"]
        Embed["Embedding API"]
    end

    iOS --> Backend
    Android --> Backend
    Web --> Backend

    Backend --> PG
    Backend --> AIEnd

    AIEnd --> PG
    AIEnd --> LLM
    AIEnd --> Embed

    Crawler --> PG
    Crawler --> OA
    Crawler --> LLM
    Crawler --> Embed
```

### 模块交互时序图

```mermaid
sequenceDiagram
    participant App as 客户端
    participant Backend as Backend (Go)
    participant AI as AI_end (FastAPI)
    participant DB as PostgreSQL
    participant LLM as LLM API

    Note over App,LLM: 用户登录流程
    App->>Backend: POST /api/auth/token
    Backend->>DB: 查询/创建用户
    Backend-->>App: JWT + Refresh Token

    Note over App,LLM: 文章浏览流程
    App->>Backend: GET /api/articles/today
    Backend->>DB: SELECT WHERE published_on = TODAY
    DB-->>Backend: 文章列表
    Backend-->>App: JSON Response

    Note over App,LLM: AI 问答流程
    App->>Backend: POST /api/ai/ask
    Backend->>Backend: 注入 user_id
    Backend->>AI: 反向代理转发
    AI->>DB: 向量相似度搜索
    DB-->>AI: 相关文章
    AI->>LLM: 生成回答
    LLM-->>AI: AI Response
    AI-->>Backend: {answer, related_articles}
    Backend-->>App: JSON Response
```

---

## 目录结构

### Backend (Go) - API 服务

```
backend/
├── cmd/server/main.go              # 应用入口，路由注册
├── internal/
│   ├── config/
│   │   └── config.go               # 配置管理（环境变量加载）
│   │
│   ├── handler/                    # HTTP 处理器层
│   │   ├── articles.go             # 文章 API (today/page/count/:id)
│   │   ├── auth.go                 # 认证 API (login/refresh/logout/me)
│   │   ├── ai.go                   # AI 代理 (转发到 ai_end)
│   │   └── profile.go              # 用户资料 API
│   │
│   ├── middleware/
│   │   └── auth.go                 # JWT 认证中间件
│   │
│   ├── model/                      # 数据模型
│   │   ├── article.go              # Article 结构体
│   │   ├── user.go                 # User 结构体
│   │   ├── session.go              # Session 结构体 (refresh token)
│   │   └── vector.go               # Vector 结构体
│   │
│   ├── repository/                 # 数据访问层
│   │   ├── article.go              # 文章 CRUD
│   │   ├── user.go                 # 用户 CRUD
│   │   └── db.go                   # 数据库连接
│   │
│   ├── service/                    # 业务逻辑层
│   │   ├── articles.go             # 文章业务逻辑
│   │   ├── auth.go                 # 认证业务逻辑
│   │   ├── cas_client.go           # 校园 SSO 验证
│   │   └── profile.go              # 用户资料业务逻辑
│   │
│   ├── migration/                  # 数据库迁移
│   │   ├── migration.go
│   │   └── versions.go
│   │
│   └── pkg/                        # 工具包
│       ├── jwt/jwt.go              # JWT 生成/验证
│       ├── hash/bcrypt.go          # 密码哈希
│       └── alog/alog.go            # 认证日志
│
├── tests/                          # 测试文件
├── Dockerfile
├── go.mod
└── go.sum
```

### Crawler (Python) - 爬虫管道

```
crawler/
├── main.py                         # 入口：解析参数，启动爬虫
├── pipeline.py                     # 核心爬取流程类 Crawler
├── fetcher.py                      # OA 系统数据获取 (列表/详情)
├── summarizer.py                   # AI 摘要生成 (OpenAI 兼容 API)
├── embeddings.py                   # 向量嵌入生成
├── storage.py                      # ArticleRepository 数据仓库
├── db.py                           # 数据库操作 (psycopg3)
├── models.py                       # 数据模型定义
├── config.py                       # 配置管理
├── utils.py                        # 工具函数
├── backfill.py                     # 历史数据回填脚本
└── services/
    └── ai_load_balancer.py         # AI 模型负载均衡器
```

### AI_end (Python) - AI 服务

```
ai_end/
├── main.py                         # CLI 交互入口
├── src/
│   ├── config/settings.py          # 环境变量配置 (dataclass)
│   ├── core/                       # 核心业务逻辑
│   │   ├── skill_parser.py             # 解析 SKILL.md (YAML front matter)
│   │   ├── db_skill_system.py          # 数据库版技能系统
│   │   ├── base_retrieval.py           # 检索基类 (embedding, 向量搜索)
│   │   ├── article_retrieval.py        # OA 文章检索 (三层混合检索)
│   │   ├── api_clients.py              # API 客户端 (LLM, Embedding, Rerank)
│   │   ├── api_queue.py                # 分层并发队列 (llm/embedding/rerank)
│   │   └── db.py                       # 数据库连接池 (asyncpg)
│   ├── chat/                       # 聊天功能
│   │   ├── client.py                   # ChatClient 主聊天逻辑
│   │   ├── handlers.py                 # 工具调用处理
│   │   ├── memory_manager.py           # 记忆管理
│   │   └── history_manager.py          # 历史管理
│   ├── api/                        # FastAPI 路由层
│   │   ├── main.py                     # 应用入口, lifespan, 路由注册
│   │   ├── chat_service.py             # SSE 流式聊天服务
│   │   └── compat_service.py           # 旧接口兼容层 (/ask, /clear_memory, /embed)
│   ├── di/                         # 依赖注入
│   │   └── providers.py               # 服务提供者
│   └── db/memory.py                # 数据访问层 (会话, 画像)
├── skills/                        # 技能定义目录
├── scripts/                       # 数据导入脚本
├── migrations/                    # 数据库迁移
└── tests/                         # 三级测试 (unit/integration/acceptance)
```

### OAP-app (React Native) - 客户端

```
OAP-app/
├── app/                            # Expo Router 页面路由
│   ├── (tabs)/                     # 底部标签页
│   │   ├── index.tsx               # 首页 (文章列表)
│   │   ├── explore.tsx             # 探索页 (AI 对话)
│   │   └── settings/               # 设置页
│   │       ├── index.tsx
│   │       ├── notifications.tsx
│   │       ├── profile-edit.tsx
│   │       └── developer.tsx
│   ├── login.tsx                   # 登录页
│   ├── _layout.tsx                 # 根布局
│   └── modal.tsx                   # 模态页
│
├── components/                     # 可复用 UI 组件
│   ├── article-card.tsx            # 文章卡片
│   ├── article-detail-sheet.tsx    # 文章详情底部抽屉
│   ├── chat-message.tsx            # 聊天消息气泡
│   ├── chat-input.tsx              # 聊天输入框
│   ├── source-card.tsx             # 相关文章卡片
│   ├── thinking-indicator.tsx      # AI 思考动画
│   └── ...
│
├── hooks/                          # 自定义 Hooks
│   ├── use-articles.ts             # 文章列表状态管理
│   ├── use-ai-chat.ts              # AI 对话状态管理
│   ├── use-auth-token.ts           # 认证令牌管理
│   ├── use-user-profile.ts         # 用户资料管理
│   └── ...
│
├── services/                       # API 服务层
│   ├── api.ts                      # API 基础配置
│   ├── articles.ts                 # 文章 API
│   ├── ai.ts                       # AI API
│   ├── auth.ts                     # 认证 API
│   └── profile.ts                  # 用户资料 API
│
├── storage/                        # 本地存储
│   ├── article-storage.ts          # 文章缓存
│   ├── chat-storage.ts             # 对话历史
│   └── auth-storage.ts             # 认证信息
│
├── types/                          # TypeScript 类型定义
│   ├── article.ts
│   ├── chat.ts
│   └── profile.ts
│
├── constants/                      # 常量配置
│   ├── palette.ts                  # 调色板
│   ├── theme.ts                    # 主题配置
│   └── shadows.ts                  # 阴影样式
│
├── notifications/                  # 推送通知
│   ├── notification-task.ts
│   ├── notification-storage.ts
│   └── notification-env.ts
│
├── App.tsx                         # 应用根组件
├── app.json                        # Expo 配置
└── package.json
```

---

## 接口通讯

### API 端点总览

```mermaid
flowchart LR
    subgraph 认证["🔐 认证 API"]
        A1["POST /api/auth/token<br/>用户登录"]
        A2["POST /api/auth/token/refresh<br/>刷新令牌"]
        A3["POST /api/auth/logout<br/>登出"]
        A4["GET /api/auth/me<br/>当前用户信息"]
    end

    subgraph 文章["📄 文章 API"]
        B1["GET /api/articles/today<br/>今日文章"]
        B2["GET /api/articles/<br/>分页文章"]
        B3["GET /api/articles/count<br/>文章总数"]
        B4["GET /api/articles/:id<br/>文章详情"]
    end

    subgraph AI["🤖 AI API"]
        C1["POST /api/ai/ask<br/>AI 问答"]
        C2["POST /api/ai/clear_memory<br/>清除记忆"]
        C3["POST /api/ai/embed<br/>生成向量"]
    end

    subgraph 用户["👤 用户 API"]
        D1["GET /api/user/profile<br/>获取资料"]
        D2["PATCH /api/user/profile<br/>更新资料"]
        D3["POST /api/user/profile/avatar<br/>上传头像"]
    end
```

### 认证流程

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant Backend as Backend
    participant CAS as 校园 CAS
    participant DB as PostgreSQL

    Client->>Backend: POST /api/auth/token<br/>{username, password}

    Backend->>DB: 查询本地用户

    alt 用户存在
        Backend->>Backend: 验证本地密码
        alt 密码正确
            Backend->>DB: 记录登录时间
            Backend->>Backend: 生成 JWT + Refresh Token
            Backend-->>Client: 登录成功
        else 密码错误
            Backend->>CAS: 校园 CAS 验证
            alt CAS 验证成功
                Backend->>DB: 更新密码哈希
                Backend->>Backend: 生成令牌
                Backend-->>Client: 登录成功
            else CAS 验证失败
                Backend-->>Client: 401 凭证错误
            end
        end
    else 用户不存在
        Backend->>CAS: 校园 CAS 验证
        alt CAS 验证成功
            Backend->>DB: 创建新用户
            Backend->>Backend: 生成令牌
            Backend-->>Client: 登录成功
        else CAS 验证失败
            Backend-->>Client: 401 凭证错误
        end
    end

    Note over Client,DB: 后续请求携带 Authorization: Bearer <access_token>
```

### 请求/响应格式

#### 登录请求

```http
POST /api/auth/token HTTP/1.1
Content-Type: application/json

{
  "username": "student001",
  "password": "********"
}
```

#### 登录响应

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "a1b2c3d4e5f6...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "username": "student001",
    "display_name": "张三",
    "roles": ["user"]
  }
}
```

#### AI 问答请求

```http
POST /api/ai/ask HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "question": "下学期奖学金申请什么时候开始？",
  "top_k": 3,
  "display_name": "张三"
}
```

#### AI 问答响应

```json
{
  "answer": "根据《关于2024-2025学年奖学金申请的通知》，下学期奖学金申请时间为2025年3月1日至3月15日...",
  "related_articles": [
    {
      "id": 123,
      "title": "关于2024-2025学年奖学金申请的通知",
      "unit": "学生处",
      "published_on": "2025-02-20",
      "similarity": 0.15,
      "content_snippet": "各学院：现将2024-2025学年奖学金申请...",
      "summary_snippet": "奖学金申请时间为3月1日至15日..."
    }
  ]
}
```

---

## 数据模型

### ER 图

```mermaid
erDiagram
    users ||--o{ sessions : "has"
    articles ||--o| vectors : "has"

    users {
        uuid id PK "用户ID"
        string username UK "用户名"
        string display_name "显示名称"
        string password_hash "密码哈希"
        string password_algo "算法(bcrypt)"
        int password_cost "哈希代价"
        string[] roles "角色列表"
        string avatar_url "头像URL"
        string[] profile_tags "标签"
        string bio "个人简介"
        boolean is_vip "VIP状态"
        timestamp vip_expired_at "VIP过期时间"
        timestamp created_at "创建时间"
        timestamp updated_at "更新时间"
        timestamp last_login_at "最后登录"
    }

    sessions {
        uuid id PK "会话ID"
        uuid user_id FK "用户ID"
        string refresh_token_sha "Refresh Token SHA256"
        timestamp expires_at "过期时间"
        timestamp revoked_at "撤销时间"
        string user_agent "UA"
        string ip "IP地址"
        timestamp created_at "创建时间"
    }

    articles {
        bigint id PK "文章ID"
        string title "标题"
        string unit "发布单位"
        string link UK "文章链接"
        date published_on "发布日期"
        text content "正文内容"
        text summary "AI摘要"
        jsonb attachments "附件信息"
        timestamp created_at "创建时间"
        timestamp updated_at "更新时间"
    }

    vectors {
        bigint id PK "向量ID"
        bigint article_id FK "文章ID"
        vector embedding "向量嵌入"
        date published_on "发布日期"
        timestamp created_at "创建时间"
        timestamp updated_at "更新时间"
    }
```

### 数据库 Schema (PostgreSQL)

```sql
-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 文章表
CREATE TABLE articles (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    unit TEXT,
    link TEXT NOT NULL UNIQUE,
    published_on DATE NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    attachments JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_articles_published_on ON articles (published_on DESC);
CREATE INDEX idx_articles_created_at ON articles (created_at DESC);

-- 向量表 (维度可配置，默认 1024)
CREATE TABLE vectors (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT REFERENCES articles(id) ON DELETE CASCADE,
    embedding vector(1024),
    published_on DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_vectors_published_on ON vectors (published_on);
CREATE UNIQUE INDEX idx_vectors_article ON vectors(article_id);

-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_algo TEXT NOT NULL DEFAULT 'bcrypt',
    password_cost INT NOT NULL DEFAULT 12,
    roles TEXT[] DEFAULT '{}',
    avatar_url TEXT,
    profile_tags TEXT[] NOT NULL DEFAULT '{}',
    bio TEXT NOT NULL DEFAULT '',
    profile_updated_at TIMESTAMPTZ,
    is_vip BOOLEAN NOT NULL DEFAULT false,
    vip_expired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- 会话表 (Refresh Token)
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_sha TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 数据流转

### 爬虫数据流

```mermaid
flowchart TD
    A[定时任务触发<br/>07:00-24:00] --> B[fetch_list<br/>获取文章列表]
    B --> C{过滤新增文章<br/>数据库去重}
    C -->|无新文章| D[结束]
    C -->|有新文章| E[fetch_detail<br/>获取文章详情]
    E --> F[Summarizer<br/>生成AI摘要]
    F --> G{摘要成功?}
    G -->|失败| H[重试最多3次]
    H --> G
    G -->|成功| I[Embedder<br/>生成向量嵌入]
    I --> J{向量成功?}
    J -->|失败| K[回滚事务]
    J -->|成功| L[事务提交<br/>存储到数据库]
    L --> M[结束]

    subgraph 数据库操作
        L --> L1[INSERT INTO articles]
        L1 --> L2[INSERT INTO vectors]
    end

    style A fill:#e1f5fe
    style L fill:#c8e6c9
    style K fill:#ffcdd2
```

### 文章查询数据流

```mermaid
flowchart TD
    A[用户打开App] --> B{检查本地缓存}
    B -->|有缓存| C[显示缓存数据]
    B -->|无缓存| D[请求 /api/articles/today]
    C --> D
    D --> E[Backend ArticleService]
    E --> F[Repository.FindToday]
    F --> G[SELECT FROM articles<br/>WHERE published_on = TODAY]
    G --> H{今天有数据?}
    H -->|有| I[返回今日文章]
    H -->|无| J[查询最新日期的文章]
    J --> I
    I --> K[返回 JSON Response]
    K --> L[客户端缓存到本地]
    L --> M[显示文章列表]

    style A fill:#e1f5fe
    style M fill:#c8e6c9
```

### AI 搜索数据流 (RAG)

```mermaid
flowchart TD
    A[用户提问] --> B[POST /api/ai/ask]
    B --> C[Backend 注入 user_id]
    C --> D[反向代理到 ai_end]
    D --> E[构建系统提示<br/>角色设定 + 当前时间]
    E --> F[加载历史对话<br/>PostgreSQL]
    F --> G[ChatClient + 技能系统执行]
    G --> H{LLM 判断<br/>是否需要检索?}
    H -->|需要| I[调用 vector_search tool]
    H -->|不需要| N[直接生成回答]

    I --> J[向量搜索 + 关键词搜索 + Rerank]
    J --> K[三层混合检索]
    K --> L[返回相关文章]
    M --> N

    N --> O[LLM 生成回答]
    O --> P[保存对话历史]
    P --> Q[返回 answer + related_articles]

    style A fill:#e1f5fe
    style Q fill:#c8e6c9
```

### 向量搜索 SQL 逻辑

```sql
-- 两阶段检索：候选集 + 时效性加权
WITH candidate AS (
    SELECT
        a.id, a.title, a.unit, a.published_on,
        a.summary, a.content,
        v.embedding <=> :query_vector AS similarity
    FROM vectors v
    JOIN articles a ON v.article_id = a.id
    ORDER BY v.embedding <=> :query_vector
    LIMIT :candidate_limit  -- 先取候选集 (top_k * 5)
)
SELECT
    id, title, unit, published_on, summary, content, similarity,
    similarity - :recency_weight * exp(-GREATEST(CURRENT_DATE - published_on, 0)::float / :half_life_days)
    AS score
FROM candidate
ORDER BY score ASC
LIMIT :top_k;
```

**时效性加权公式**：
```
final_score = similarity - recency_weight × exp(-days_old / half_life)
```
- `similarity`：向量余弦距离（越小越相似）
- `recency_weight`：时效权重（配置项）
- `half_life`：半衰期天数（配置项）
- 新文章获得更低的 score，排名更靠前

---

## 关键技术实现

### 1. JWT 认证机制

```go
// 生成 Token
func GenerateToken(secret, userID, username, displayName string, roles []string, ttl int64) (string, error) {
    claims := jwt.MapClaims{
        "sub":          userID,
        "username":     username,
        "display_name": displayName,
        "roles":        roles,
        "exp":          time.Now().Add(time.Duration(ttl) * time.Second).Unix(),
        "iat":          time.Now().Unix(),
    }
    token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
    return token.SignedString([]byte(secret))
}

// 中间件验证
func AuthRequired(secret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        token := extractToken(c.GetHeader("Authorization"))
        claims, err := jwt.VerifyToken(secret, token)
        if err != nil {
            c.AbortWithStatusJSON(401, gin.H{"error": "unauthorized"})
            return
        }
        c.Set("user_id", claims.UserID)
        c.Next()
    }
}
```

### 2. AI 负载均衡

```python
class AILoadBalancer:
    """AI 模型负载均衡器，支持多模型配置和 429 错误自动切换"""

    def __init__(self, models: list[ModelConfig]):
        self.models = models
        self.current_index = 0
        self.rate_limited: dict[str, float] = {}  # 模型 -> 冷却结束时间

    def get_next_model(self) -> ModelConfig | None:
        """轮询选择可用模型，跳过限流中的模型"""
        now = time.time()
        for _ in range(len(self.models)):
            model = self.models[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.models)

            # 检查是否在冷却期
            cooldown_end = self.rate_limited.get(model.base_url, 0)
            if now > cooldown_end:
                return model

        return None  # 所有模型都不可用

    def mark_model_429(self, model: ModelConfig):
        """标记模型为限流状态，60秒冷却"""
        self.rate_limited[model.base_url] = time.time() + 60
```

### 3. 技能系统 (Function Calling)

```python
# AI 通过 OpenAI Function Calling 调用技能
# ChatClient 内部管理技能激活和二级工具加载

# 一级工具：技能列表 + read_reference
tools = [
    {"type": "function", "function": {"name": "article-retrieval"}},
    {"type": "function", "function": {"name": "read_reference"}},
]

# AI 调用技能后，动态加载二级工具
# search_articles, grep_article, grep_articles
secondary_tools = skill_system.get_tools_for_skill(skill_name)
```

### 4. 前端状态管理

```typescript
// hooks/use-articles.ts
export function useArticles(token?: string | null) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [nextBeforeDate, setNextBeforeDate] = useState<string | null>(null);
  const [nextBeforeId, setNextBeforeId] = useState<number | null>(null);

  // 加载今日文章（乐观更新）
  const loadArticles = useCallback(async () => {
    // 1. 先显示本地缓存
    const cached = await getCachedArticlesByDate(getTodayDateString());
    if (cached) setArticles(cached);

    // 2. 请求服务器最新数据
    const response = await fetchTodayArticles(token);
    setArticles(response.articles);
    setHasMore(response.has_more);

    // 3. 更新缓存
    await setCachedArticlesByDate(getTodayDateString(), response.articles);

    // 4. 预缓存文章详情
    void prefetchArticleDetails(response.articles);
  }, [token]);

  // 无限滚动加载更多
  const loadMoreArticles = useCallback(async () => {
    if (!hasMore || !nextBeforeId) return;
    const response = await fetchArticlesPage(nextBeforeDate, nextBeforeId, token);
    setArticles(prev => [...prev, ...response.articles]);
  }, [hasMore, nextBeforeId, token]);

  return { articles, isLoading, hasMore, loadArticles, loadMoreArticles };
}
```

---

## 缓存策略

### 缓存架构

```mermaid
flowchart LR
    subgraph 客户端缓存["📱 客户端缓存 (AsyncStorage)"]
        C1["articles:{date}<br/>文章列表"]
        C2["article:{id}<br/>文章详情"]
        C3["chat_history<br/>对话历史"]
        C4["auth_token<br/>认证信息"]
    end

    subgraph 服务端缓存["🖥️ 服务端缓存"]
        S1["ai:mem:{user_id}<br/>AI对话记忆<br/>TTL: 24h"]
    end

    subgraph HTTP缓存["🌐 HTTP 缓存"]
        H1["ETag<br/>文章列表/详情"]
        H2["Cache-Control<br/>max-age: 3600"]
    end
```

### 缓存策略详解

| 缓存层 | 存储位置 | Key 格式 | TTL | 策略 |
|--------|----------|----------|-----|------|
| 文章列表 (今日) | AsyncStorage | `articles:{YYYY-MM-DD}` | 持久化 | 乐观更新：先显示缓存，后刷新 |
| 文章详情 | AsyncStorage | `article:{id}` | 持久化 | 按需缓存，打开详情时预缓存 |
| AI 对话历史 | AsyncStorage | `chat_history` | 持久化 | 本地保存，App 启动时恢复 |
| AI 短期记忆 | PostgreSQL | `conversations` 表 | 持久化 | 服务端存储，JSONB 格式 |
| HTTP ETag | HTTP Header | MD5(Response) | - | 304 Not Modified |

---

## 部署架构

### Docker Compose 部署

```yaml
# docker-compose.yml
services:
  postgres:
    image: ankane/pgvector:latest
    environment:
      POSTGRES_DB: oa-reader
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5430:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgres://${DB_USER}:${DB_PASSWORD}@postgres:5432/oa-reader
      AUTH_JWT_SECRET: ${JWT_SECRET}
      AI_END_URL: http://ai_end:4421
    ports:
      - "4420:4420"
    depends_on:
      - postgres

  ai_end:
    build: ./ai_end
    environment:
      DATABASE_URL: postgres://${DB_USER}:${DB_PASSWORD}@postgres:5432/oa-reader
    ports:
      - "4421:4421"
    depends_on:
      - postgres

volumes:
  postgres_data:
```

### 部署架构图

```mermaid
flowchart TB
    subgraph 生产环境
        subgraph Docker["Docker Compose"]
            PG[("PostgreSQL<br/>+ pgvector<br/>:5430")]
            Backend["Backend (Go)<br/>:4420"]
            AIEnd["AI_end (FastAPI)<br/>:4421"]
        end

        subgraph 外部服务["外部服务"]
            LLM["LLM API<br/>(OpenAI 兼容)"]
            Embed["Embedding API"]
            OA["OA 系统"]
        end

        subgraph 爬虫["定时任务"]
            Crawler["Crawler<br/>(Cron Job)"]
        end
    end

    Client["客户端<br/>(iOS/Android/Web)"] -->|HTTPS| Backend
    Backend --> PG
    Backend --> AIEnd
    AIEnd --> PG
    AIEnd --> LLM
    AIEnd --> Embed
    Crawler --> PG
    Crawler --> OA
    Crawler --> LLM
    Crawler --> Embed
```

### 环境变量配置

```bash
# backend/.env
DATABASE_URL=postgres://user:pass@localhost:5430/oa-reader
AUTH_JWT_SECRET=your-jwt-secret-key
AUTH_REFRESH_HASH_KEY=your-refresh-hash-key
AUTH_ACCESS_TOKEN_TTL=1h
AUTH_REFRESH_TOKEN_TTL=168h
AUTH_PASSWORD_COST=12
AUTH_ALLOW_AUTO_USER_CREATION=true
CAMPUS_AUTH_ENABLED=true
CAMPUS_AUTH_URL=http://a.stu.edu.cn/ac_portal/login.php
AI_END_URL=http://localhost:4421

# ai_end/.env
DATABASE_URL=postgres://user:pass@localhost:5430/oa-reader
AI_BASE_URL=https://api.openai.com/v1/chat/completions
AI_MODEL=gpt-4o-mini
API_KEY=your-api-key
EMBED_BASE_URL=https://api.openai.com/v1/embeddings
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=your-api-key
EMBED_DIM=1024

# crawler/.env
DATABASE_URL=postgres://user:pass@localhost:5430/oa-reader
AI_BASE_URL=https://api.openai.com/v1/chat/completions
AI_MODEL=gpt-4o-mini
API_KEY=your-api-key
EMBED_BASE_URL=https://api.openai.com/v1/embeddings
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=your-api-key

# OAP-app/.env
EXPO_PUBLIC_API_BASE_URL=https://api.example.com/api
```

---

## 附录

### 常用命令

```bash
# 后端
cd backend && go run cmd/server/main.go

# AI 服务
cd ai_end && python app.py

# 爬虫
cd crawler && python main.py                    # 当天数据
cd crawler && python main.py --date 2024-01-01  # 指定日期

# 客户端
cd OAP-app && npm start
cd OAP-app && npm run android
cd OAP-app && npm run ios
cd OAP-app && npm run web

# 测试
cd backend && go test ./...
cd ai_end && pytest
cd crawler && pytest
```

### 相关文档

- [API 文档](./api_documentation.md)
- [配置说明](./configuration.md)
- [部署指南](./deployment.md)

---

*本文档由 Claude 自动生成，基于项目源代码分析*
