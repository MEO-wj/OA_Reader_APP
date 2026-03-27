# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## TOP RULES
must reply in chinese
have to use superpower
must use TDD(REG)
优先复用项目中已有的组件
如果存在多个方案优先输出未来技术债最少的方案
always show me some of plan, and recommand me a plan whitch has lower tech-debt plan

## Project Overview

OA-Reader (智能校园OA助手) - 一款为学校OA系统打造的智能移动助手，提供AI摘要、智能搜索和推送通知功能。项目采用微服务架构，分为四个核心模块：

- **OAP-app**: React Native 多端客户端 (Expo 54)
- **backend**: Go API 服务 (Gin框架，端口4420)
- **ai_end**: Python AI 服务 (Flask + LangGraph，端口4421)
- **crawler**: Python 数据爬取与处理管道

## Common Commands

### Frontend (OAP-app)
```bash
cd OAP-app
npm install          # 安装依赖
npm start            # 启动开发服务器
npm run android      # Android 开发
npm run ios          # iOS 开发
npm run web          # Web 开发
npm run lint         # ESLint 检查
```

### Backend (Go)
```bash
cd backend
go run cmd/server/main.go      # 启动服务 (http://localhost:4420)
go test ./...                   # 运行所有测试
go test ./internal/handler/...  # 运行特定包测试
go test -v -run TestName ./...  # 运行单个测试
```

### AI Service (ai_end)
```bash
cd ai_end
uv sync              # 安装依赖
python app.py        # 启动服务 (http://localhost:4421)
uv run pytest        # 运行测试
```

### Crawler
```bash
cd crawler
uv sync                           # 安装依赖
python main.py                    # 运行当天爬取
python main.py --date 2024-01-01  # 指定日期爬取
uv run pytest                     # 运行测试
```

### Docker (全栈部署)
```bash
docker-compose up -d              # 启动所有服务
docker-compose up -d postgres backend  # 仅启动数据库和后端
```

## Architecture

### 模块职责

| 模块 | 技术栈 | 端口 | 职责 |
|------|--------|------|------|
| backend | Go + Gin + GORM | 4420 | 认证、文章查询、用户资料、AI代理 |
| ai_end | Python + Flask + LangGraph | 4421 | RAG问答、向量搜索、嵌入生成 |
| crawler | Python + psycopg | - | OA爬取、AI摘要、向量生成 |
| OAP-app | React Native + Expo | - | iOS/Android/Web 客户端 |

### 数据流

```
用户请求 → Backend (Go:4420)
              ├── /api/auth/*   → 认证服务 (校园CAS + JWT)
              ├── /api/articles/* → PostgreSQL (文章表)
              ├── /api/user/*   → PostgreSQL (用户表)
              └── /api/ai/*     → 反向代理 → AI_end (Flask:4421)
                                           ├── 向量搜索 (pgvector)
                                           └── LLM 调用

爬虫定时任务 → OA系统 → 获取文章 → AI摘要 → 向量嵌入 → PostgreSQL
```

### Backend 结构 (Go)
```
backend/
├── cmd/server/main.go          # 应用入口，路由注册
├── internal/
│   ├── handler/                # HTTP 处理器 (articles, auth, ai, profile)
│   ├── middleware/auth.go      # JWT 认证中间件
│   ├── model/                  # 数据模型 (Article, User, Session)
│   ├── repository/             # 数据访问层 (GORM)
│   ├── service/                # 业务逻辑层
│   │   ├── auth.go             # 认证逻辑 (CAS验证 + JWT)
│   │   ├── articles.go         # 文章查询
│   │   └── cas_client.go       # 校园SSO客户端
│   ├── migration/              # 数据库迁移
│   └── pkg/                    # 工具包 (jwt, hash, alog)
└── tests/                      # 集成测试
```

### AI_end 结构 (Python)
```
ai_end/
├── app.py                      # Flask 应用，RAG Agent 实现
├── config.py                   # 配置管理
└── services/
    ├── load_balancer.py        # AI 模型负载均衡
    └── queue.py                # 请求队列
```

### Crawler 结构 (Python)
```
crawler/
├── main.py                     # 入口
├── pipeline.py                 # 爬取流程类 Crawler
├── fetcher.py                  # OA 数据获取 (列表/详情)
├── summarizer.py               # AI 摘要生成 (负载均衡)
├── embeddings.py               # 向量嵌入生成
├── storage.py                  # ArticleRepository
├── db.py                       # 数据库操作 (psycopg3)
└── services/ai_load_balancer.py
```

### Frontend 结构 (React Native)
```
OAP-app/
├── app/                        # Expo Router 页面路由
│   ├── (tabs)/                 # 底部标签页 (index=首页, explore=AI对话)
│   └── login.tsx               # 登录页
├── components/                 # 可复用UI组件
├── hooks/                      # useArticles, useAiChat, useAuthToken
├── services/                   # API 服务层 (articles.ts, ai.ts, auth.ts)
└── storage/                    # AsyncStorage 封装
```

## Key Technical Details

### 认证流程
1. 用户登录 → Backend 验证本地密码
2. 本地密码错误/用户不存在 → 调用校园CAS验证
3. CAS验证成功 → 创建/更新用户，生成JWT + Refresh Token
4. Refresh Token 存储SHA256哈希到 sessions 表

### AI 问答 (RAG)
1. 用户提问 → Backend 反向代理 → AI_end
2. AI_end 构建系统提示 + 加载历史对话 (Redis 24h TTL)
3. LangGraph Agent 判断是否需要检索
4. 需要检索 → pgvector 向量相似度搜索 → 时效性加权排序
5. LLM 生成回答 → 返回 answer + related_articles

### 向量搜索时效性加权
```sql
-- 越新的文章排名越靠前
score = similarity - recency_weight * exp(-days_old / half_life)
```

### 爬虫运行时段
- 当天数据：仅在 07:00-24:00 运行
- 历史数据：随时可运行 (`--date` 参数)

### 数据库表
- `articles`: 文章表 (标题、正文、摘要、发布日期)
- `vectors`: 向量表 (article_id, embedding vector(1024))
- `users`: 用户表 (用户名、密码哈希、显示名、头像)
- `sessions`: 会话表 (refresh_token_sha, expires_at)

## Environment Configuration

| 服务 | 配置文件 | 模板 |
|------|----------|------|
| backend | `backend/.env` | 环境变量直接加载 |
| ai_end | `ai_end/.env` | `ai_end/env.example` |
| crawler | `crawler/.env` | `crawler/env.example` |
| OAP-app | `OAP-app/.env` | `OAP-app/.env.example` |

### 核心环境变量

**backend/.env**:
```
DATABASE_URL=postgres://user:pass@localhost:5430/oa-reader?sslmode=disable
AUTH_JWT_SECRET=your-jwt-secret
AUTH_REFRESH_HASH_KEY=your-hash-key
CAMPUS_AUTH_ENABLED=true
CAMPUS_AUTH_URL=http://a.stu.edu.cn/ac_portal/login.php
AI_END_URL=http://localhost:4421
```

**ai_end/.env & crawler/.env**:
```
DATABASE_URL=postgres://user:pass@localhost:5430/oa-reader
AI_BASE_URL=https://api.openai.com/v1/chat/completions
AI_MODEL=gpt-4o-mini
API_KEY=your-api-key
EMBED_BASE_URL=https://api.openai.com/v1/embeddings
EMBED_MODEL=text-embedding-3-small
EMBED_DIM=1024
```

**OAP-app/.env**:
```
EXPO_PUBLIC_API_BASE_URL=http://localhost:4420/api
```

## Development Notes

- Backend 使用 Go 1.21+，包管理使用 Go modules
- AI_end 和 Crawler 使用 Python 3.11+，包管理使用 uv
- 数据库需支持 pgvector 扩展 (使用 `ankane/pgvector` Docker 镜像)
- 前端使用 Expo Router 进行文件路由
- 所有服务默认连接到 Docker Compose 中的 postgres 容器