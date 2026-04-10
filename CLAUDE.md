# CLAUDE.md

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
- **ai_end**: Python AI 服务 (FastAPI + 技能系统，端口4421)
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
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 4421  # API 模式启动
uv run main.py       # CLI 交互模式
uv run pytest        # 运行所有测试
uv run pytest tests/unit/test_skill_system.py -v   # 运行单个单元测试
uv run pytest tests/integration/ -v                 # 运行集成测试
uv run pytest tests/acceptance/ -v                  # 运行验收测试
uv run pytest tests/ --cov=src --cov-report=term    # 测试覆盖率
uv run pytest -m "not integration"                  # 跳过集成测试
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
docker-compose up -d              # 启动 postgres + backend
docker-compose up -d postgres backend  # 仅启动数据库和后端
```

## Architecture

### 模块职责

| 模块 | 技术栈 | 端口 | 职责 |
|------|--------|------|------|
| backend | Go + Gin + GORM | 4420 | 认证、文章查询、用户资料、AI代理 |
| ai_end | Python + FastAPI + 技能系统 | 4421 | RAG问答、向量搜索、技能调用、SSE流式响应 |
| crawler | Python + psycopg | - | OA爬取、AI摘要、向量生成 |
| OAP-app | React Native + Expo | - | iOS/Android/Web 客户端 |

### 数据流

```
用户请求 → Backend (Go:4420)
              ├── /api/auth/*   → 认证服务 (校园CAS + JWT)
              ├── /api/articles/* → PostgreSQL (文章表)
              ├── /api/user/*   → PostgreSQL (用户表)
              └── /api/ai/*     → 反向代理 → AI_end (FastAPI:4421)
                                           ├── /chat (SSE流式)
                                           ├── /ask (旧兼容, JSON)
                                           ├── /skills
                                           └── /chat/sessions/*

爬虫定时任务 → OA系统 → 获取文章 → AI摘要 → 向量嵌入 → PostgreSQL
```

### AI_end 架构 (重构后，分层设计)

```
ai_end/
├── src/
│   ├── config/settings.py    # 环境变量配置 (dataclass)
│   ├── core/                 # 核心业务逻辑
│   │   ├── skill_system.py       # 文件系统版技能系统 (已废弃)
│   │   ├── db_skill_system.py    # 数据库版技能系统 (推荐)
│   │   ├── base_retrieval.py     # 检索基类 (embedding, 向量搜索)
│   │   ├── article_retrieval.py  # OA文章检索 (search_articles, grep_article)
│   │   ├── response_composer.py  # 检索结果编排 (上下文块, 来源引用)
│   │   ├── document_content.py   # 文章内容获取与匹配
│   │   ├── api_clients.py        # API 客户端 (LLM, Embedding, Rerank)
│   │   ├── api_queue.py          # 分层并发队列 (llm/embedding/rerank 分 lane)
│   │   ├── db.py                 # 数据库连接池 (asyncpg)
│   │   ├── hash_utils.py         # 哈希工具
│   │   ├── skill_adapter.py      # 技能适配器 (SkillBackend 枚举)
│   │   └── tool_activation.py    # 工具激活逻辑
│   ├── chat/                 # 聊天功能
│   │   ├── client.py              # ChatClient 主聊天逻辑
│   │   ├── handlers.py            # 工具调用处理
│   │   ├── context_truncator.py   # 工具输出截断
│   │   ├── context_budget.py      # 上下文预算
│   │   ├── compact.py             # 对话压缩
│   │   ├── history_manager.py     # 历史管理
│   │   ├── memory_manager.py      # 记忆管理
│   │   ├── prompts_runtime.py     # 运行时提示词
│   │   └── utils.py              # 工具函数
│   ├── api/                  # FastAPI 路由层
│   │   ├── main.py               # 应用入口, lifespan, 路由注册
│   │   ├── admin.py              # 管理路由
│   │   ├── chat_service.py       # SSE 流式聊天服务
│   │   ├── models.py             # 新版请求/响应模型
│   │   ├── compat_service.py     # 旧接口兼容层 (/ask, /clear_memory, /embed)
│   │   ├── compat_models.py      # 旧接口数据模型
│   │   ├── import_decider.py     # 自动导入决策
│   │   └── import_probe.py       # 导入探测
│   ├── di/                   # 依赖注入
│   │   ├── container.py          # DI 容器
│   │   └── providers.py          # 服务提供者
│   ├── db/memory.py          # 数据访问层 (会话, 画像, async)
│   └── ui/console.py         # CLI 终端输出
├── skills/                    # 技能定义目录
│   └── article-retrieval/
│       ├── SKILL.md           # 技能定义 (YAML front matter + 内容)
│       └── TOOLS.md           # 工具定义
├── migrations/                # 数据库迁移
├── tests/                     # 三级测试
│   ├── unit/                  # 单元测试 (不依赖外部)
│   ├── integration/           # 集成测试 (需数据库等)
│   └── acceptance/            # 验收测试 (端到端)
└── main.py                    # CLI 入口
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

## Key Technical Details

### 认证流程
1. 用户登录 → Backend 验证本地密码
2. 本地密码错误/用户不存在 → 调用校园CAS验证
3. CAS验证成功 → 创建/更新用户，生成JWT + Refresh Token
4. Refresh Token 存储SHA256哈希到 sessions 表

### AI 问答 (技能系统 + 三层检索)
1. 用户提问 → Backend 反向代理 → AI_end `/chat` (SSE) 或 `/ask` (兼容)
2. AI_end 加载技能定义 → 构建系统提示 + 对话历史 (PostgreSQL)
3. AI 通过 Function Calling 决定调用技能工具
4. **三层检索策略**:
   - Layer 1: EBD 向量搜索 (vectors JOIN articles, top-20)
   - Layer 2: 关键词模糊搜索 (pg_trgm, top-20)
   - Layer 3: Rerank 重排序 (bge-reranker-v2-m3, top-k)
5. ResponseComposer 编排上下文块和来源引用
6. LLM 生成回答 → SSE 流式返回 (新接口) 或 JSON 返回 (兼容接口)

### 旧接口兼容
- `/ask` → CompatService 桥接到新 ChatClient 事件流，返回 JSON
- `/clear_memory` → 清空用户聊天历史与画像
- `/embed` → 向量嵌入生成

### 技能系统
- 技能定义在 `skills/` 目录下，每个子目录一个 `SKILL.md`
- SKILL.md 使用 YAML front matter 定义元数据 (name, description, verification_token)
- 技能信息转换为 OpenAI Function Calling 格式
- 支持数据库版 (DbSkillSystem) 和文件系统版 (SkillSystem) 两种加载方式
- `read_reference` 工具支持按需读取技能目录下的参考文件

### 并发治理
- 分层队列: `llm`、`embedding`、`rerank` 分 lane 控制并发
- LLM 并发: 2, Embedding 并发: 6, Rerank 并发: 2
- 关闭顺序: `close_clients → close_resources → close_pool → close_api_queue → shutdown_tool_loop`

### 爬虫运行时段
- 当天数据：仅在 07:00-24:00 运行
- 历史数据：随时可运行 (`--date` 参数)

### 数据库表
- `articles`: 文章表 (标题、正文、摘要、发布日期)
- `vectors`: 向量表 (article_id, embedding vector(1024), ON DELETE CASCADE)
- `users`: 用户表 (用户名、密码哈希、显示名、头像)
- `sessions`: 会话表 (refresh_token_sha, expires_at)
- `conversations`: 会话记录 (user_id UUID, conversation_id, title, messages JSONB)
- `conversation_sessions`: 会话元信息 (user_id UUID, conversation_id, title, created_at, updated_at)
- `user_profiles`: 用户画像 (user_id UUID, portrait_text, knowledge_text, preferences JSONB)
- `skills`: 技能定义 (name, description, verification_token, metadata, content, tools, is_static)
- `skill_references`: 技能参考资料 (skill_id FK, file_path, content)

## Environment Configuration

### backend/.env
```
DATABASE_URL=postgres://user:pass@localhost:5430/oa-reader?sslmode=disable
AUTH_JWT_SECRET=your-jwt-secret
AUTH_REFRESH_HASH_KEY=your-hash-key
CAMPUS_AUTH_ENABLED=true
CAMPUS_AUTH_URL=http://a.stu.edu.cn/ac_portal/login.php
AI_END_URL=http://localhost:4421
```

### ai_end/.env (重构后变量名已变更)
```
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=deepseek-v3.2
DB_HOST=localhost
DB_PORT=5432
DB_USER=oa
DB_PASSWORD=oa
DB_NAME=oa
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_MAX_CANDIDATES=40
AUTO_MIGRATE=true
AUTO_IMPORT=true
```

### OAP-app/.env
```
EXPO_PUBLIC_API_BASE_URL=http://localhost:4420/api
```

## Development Notes

- Backend 使用 Go 1.21+，包管理使用 Go modules
- AI_end 和 Crawler 使用 Python 3.11+，包管理使用 uv
- AI_end 测试分三级: `unit/` (纯逻辑), `integration/` (需外部依赖), `acceptance/` (端到端)
- AI_end 使用 `asyncio_mode = "auto"`，测试无需手动 `@pytest.mark.asyncio`
- 数据库需支持 pgvector 扩展 (使用 `ankane/pgvector` Docker 镜像)
- Docker Compose 仅编排 postgres + backend，ai_end 需独立启动
- 所有服务默认连接到 Docker Compose 中的 postgres 容器
