# Backend Go 重构设计方案

**日期**: 2026-03-19
**状态**: 已批准
**技术栈**: Go + Gin + GORM + PostgreSQL/pgvector

---

## 1. 背景与目标

将现有 Python Flask 后端（`backend/`）重构为 Go 语言版本，保持：
- API 完全兼容（前端无需修改）
- AI 服务独立部署（端口 4421），后端代理转发
- 现有数据库结构不变

---

## 2. 架构图

```
前端 (移动端)
    │
    ▼
┌─────────────────────────────────┐
│  Go Backend (端口 4420, 对外)   │
│                                 │
│  ├─ /api/auth/*                 │
│  ├─ /api/articles/*             │
│  └─ /api/ai/*  (代理转发)  ────▶│───▶ AI End (端口 4421, 仅内网)
│                                 │        (不暴露给外部)
└─────────────────────────────────┘
```

---

## 3. 项目结构

```
backend-go/
├── cmd/
│   └── server/
│       └── main.go           # 入口
├── internal/
│   ├── config/
│   │   └── config.go         # 配置加载 (.env → 结构体)
│   ├── handler/
│   │   ├── auth.go           # 认证 handler
│   │   ├── articles.go       # 文章 handler
│   │   └── ai.go             # AI 代理 handler
│   ├── service/
│   │   ├── auth.go           # 认证业务逻辑
│   │   └── articles.go       # 文章业务逻辑
│   ├── repository/
│   │   ├── user.go           # 用户数据访问
│   │   └── article.go        # 文章数据访问
│   ├── model/
│   │   ├── user.go           # User, Session 模型
│   │   └── article.go        # Article 模型
│   ├── middleware/
│   │   ├── auth.go           # JWT 认证中间件
│   │   ├── limiter.go        # 限流中间件
│   │   └── cors.go           # CORS 中间件
│   └── pkg/
│       ├── jwt/
│       │   └── jwt.go         # JWT 工具
│       └── hash/
│           └── bcrypt.go      # bcrypt 工具
├── migrations/
│   └── init.sql              # 数据库初始化 SQL
├── .env.example
├── go.mod
└── go.sum
```

---

## 4. API 兼容矩阵

### 4.1 认证接口 `/api/auth`

| 方法 | 路径 | 请求体 | 响应 |
|------|------|--------|------|
| POST | `/api/auth/token` | `{username, password}` | `{access_token, refresh_token, token_type, expires_in, user}` |
| POST | `/api/auth/token/refresh` | `{refresh_token}` | 同上 |
| POST | `/api/auth/logout` | `{refresh_token}` | `{ok: true}` |
| GET | `/api/auth/me` | - (Bearer Token) | `{id, username, display_name, roles}` |

### 4.2 文章接口 `/api/articles`

| 方法 | 路径 | 查询参数 | 响应 |
|------|------|----------|------|
| GET | `/api/articles/today` | - | `{articles:[], has_more, next_before_date, next_before_id}` |
| GET | `/api/articles/` | `v=1\|2`, `before_date`, `before_id`, `limit` | 同上 |
| GET | `/api/articles/count` | - | `{total}` |
| GET | `/api/articles/<id>` | - | Article 对象含 `content` |

**分页逻辑**:
- `v=1`: `before_id` 分页
- `v=2`: `(before_date, before_id)` 复合游标分页

### 4.3 AI 接口 `/api/ai` (代理)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai/ask` | 代理到 AI End `/ask` |
| POST | `/api/ai/clear_memory` | 代理到 AI End `/clear_memory` |
| POST | `/api/ai/embed` | 代理到 AI End `/embed` |

### 4.4 健康检查

| 方法 | 路径 | 响应 |
|------|------|------|
| GET | `/api/health` | `{status: "ok"}` |

---

## 5. 数据模型

### 5.1 Users

```go
type User struct {
    ID           string    `gorm:"type:uuid;primaryKey"`
    Username     string    `gorm:"uniqueIndex;not null"`
    DisplayName  string    `gorm:"not null"`
    PasswordHash string    `gorm:"not null"`
    PasswordAlgo string    `gorm:"not null;default:bcrypt"`
    PasswordCost int       `gorm:"not null;default:12"`
    Roles        []string  `gorm:"type:text[]"`
    CreatedAt    time.Time
    UpdatedAt    time.Time
    LastLoginAt  *time.Time
}
```

### 5.2 Sessions

```go
type Session struct {
    ID              string    `gorm:"type:uuid;primaryKey"`
    UserID          string    `gorm:"type:uuid;index"`
    RefreshTokenSHA string    `gorm:"uniqueIndex;not null"`
    ExpiresAt       time.Time `gorm:"not null"`
    UserAgent       string
    IP              string
    RevokedAt       *time.Time
    CreatedAt       time.Time
}
```

### 5.3 Articles

```go
type Article struct {
    ID          uint64    `gorm:"primaryKey"`
    Title       string    `gorm:"not null"`
    Unit        string
    Link        string    `gorm:"uniqueIndex;not null"`
    PublishedOn time.Time `gorm:"index;not null"`
    Content     string    `gorm:"not null"`
    Summary     string    `gorm:"not null"`
    Attachments JSONArray `gorm:"type:jsonb;default:'[]'"`
    CreatedAt   time.Time
    UpdatedAt   time.Time
}
```

### 5.4 Vectors (pgvector)

```go
type Vector struct {
    ID          uint64    `gorm:"primaryKey"`
    ArticleID   uint64    `gorm:"index"`
    Embedding   Vector    `gorm:"type:vector(1536)"`
    PublishedOn time.Time
    CreatedAt   time.Time
    UpdatedAt   time.Time
}
```

---

## 6. 核心实现细节

### 6.1 配置管理

使用 `github.com/spf13/viper` 加载 `.env` 文件：

```go
type Config struct {
    DatabaseURL          string
    AuthJWTSecret        string
    AuthRefreshHashKey   string
    AuthAccessTokenTTL   time.Duration
    AuthRefreshTokenTTL  time.Duration
    AuthPasswordCost     int
    AuthAllowAutoUser    bool
    CampusAuthEnabled    bool
    CampusAuthURL        string
    CampusAuthTimeout    int
    CORSAllowOrigins     []string
    RateLimitPerDay      int
    RateLimitPerHour     int
    AIEndURL             string
}
```

### 6.2 JWT 实现

- Access Token: 标准 JWT (HS256)，包含 `sub`, `name`, `roles`, `iat`, `exp`
- Refresh Token: 48 字节随机值，存储 SHA256 哈希

### 6.3 CAS 认证

保持现有流程：
1. 解析校园 SSO 登录页表单
2. 提取 hidden inputs + form action
3. POST 用户凭证到 SSO
4. 提取 ST ticket
5. 验证 ticket 获取用户信息

### 6.4 ETag 缓存

文章响应使用 ETag + `If-None-Match` 实现条件请求：
- 生成: `MD5(json.Marshal(articles))`
- 响应: `ETag` header + `Cache-Control: max-age=3600, public`
- 匹配: 返回 `304 Not Modified`

### 6.5 限流

使用 `github.com/ulule/limiter/v3`：
- 内存存储（可扩展为 Redis）
- 支持按 IP/用户维度

---

## 7. 依赖清单

```toml
github.com/gin-gonic/gin           # Web 框架
gorm.io/gorm                       # ORM
gorm.io/driver/postgres            # PostgreSQL 驱动
github.com/vectorval/go-pgvector   # pgvector 支持 (待确认具体库)
github.com/golang-jwt/jwt/v5       # JWT
golang.org/x/crypto/bcrypt          # bcrypt
github.com/spf13/viper             # 配置管理
github.com/ulule/limiter/v3        # 限流
github.com/gin-contrib/cors        # CORS
github.com/google/uuid             # UUID
github.com/msgpack/msgpack-go      # 序列号 (可选)
```

---

## 8. 数据库迁移

启动时使用 GORM AutoMigrate 自动创建表：

```go
db.AutoMigrate(&User{}, &Session{}, &Article{}, &Vector{})
```

初始 SQL (migrations/init.sql) 用于创建 pgvector 扩展：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 9. 测试策略

- 保持 API 兼容意味着前端测试用例可直接验证
- 重点测试：认证流程、分页逻辑、ETag 缓存
- 使用 `net/http/httptest` 进行 handler 测试

---

## 10. 风险与注意事项

1. **pgvector Go 客户端**: 需要确认可用的 Go pgvector 库，当前 Python 使用 `pgvector` 扩展
2. **bcrypt 兼容性**: Go bcrypt 与 Python bcrypt 输出兼容
3. **CAS SSO 稳定性**: 依赖外部 SSO 网站，需考虑超时和错误处理
