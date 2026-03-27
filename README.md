# OAP - 智能校园OA助手

> 告别错过，让重要通知触手可及

一款为学校OA系统量身打造的智能移动助手，将学校OA装进口袋，并赋予它智慧。

## ✨ 核心特性

### 🤖 智能摘要
海量通知，一秒读懂。利用AI将冗长文章自动提炼为清晰摘要，为你节省宝贵时间。

### 🔍 AI智能搜索
想问什么，就问什么。不再依赖关键词，用自然语言对话，直达你需要的通知。基于RAG（检索增强生成）技术，精准定位相关文章。

### 📱 多端即时推送
重要通知，主动找你。关键信息即时推送到手机，像私人秘书一样确保你永不缺席。

## 🏗️ 项目架构

本项目采用现代化的微服务架构，分为三个核心模块：

```
OAP/
├── OAP-app/          # React Native 多端客户端
├── backend/           # Flask API 服务
├── crawler/           # 数据爬取与处理管道
└── docs/              # 项目文档
```

### 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   iOS App    │  │  Android App │  │   Web App    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                    ┌────────▼────────┐
                    │   API Gateway   │
                    │   (Flask API)   │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐    ┌──────▼──────┐    ┌─────▼─────┐
    │ PostgreSQL │    │    Redis    │    │   AI服务   │
    │  + pgvector│    │   缓存层     │    │  (LLM)    │
    └───────────┘    └─────────────┘    └───────────┘
          │
    ┌─────▼─────┐
    │  Crawler  │
    │  爬虫管道  │
    └───────────┘
```

### 模块详解

#### 1. OAP-app - React Native 多端客户端

**技术栈：**
- React Native 0.81.5 + Expo 54
- TypeScript
- Expo Router（文件路由）
- Expo Notifications（推送通知）

**核心功能：**
- **文章浏览**：查看OA通知列表和详情
- **AI对话**：自然语言搜索相关文章
- **推送通知**：接收重要通知提醒
- **多端适配**：iOS、Android、Web统一代码库

**数据流：**
```
用户操作 → UI组件 → Hooks → Services → API请求
         ↓
    本地存储（AsyncStorage）
         ↓
    推送通知（Expo Notifications）
```

**关键组件：**
- `app/` - 页面路由（首页、探索、设置）
- `components/` - 可复用UI组件
- `hooks/` - 自定义React Hooks（useAiChat、useArticles等）
- `services/` - API服务层
- `storage/` - 本地数据持久化

#### 2. backend - Flask API 服务

**技术栈：**
- Flask 3.0.0+
- PostgreSQL + pgvector（向量数据库）
- Redis（缓存）
- JWT（认证）
- LangGraph + LangChain（AI Agent）

**核心功能：**
- **认证服务**：用户登录、JWT令牌管理
- **文章服务**：文章列表、详情查询（支持增量更新）
- **AI服务**：基于向量的智能问答
- **缓存服务**：Redis缓存加速响应

**数据流：**
```
API请求 → 路由层 → 业务逻辑层 → 数据访问层
         ↓
    Redis缓存（优先）
         ↓
    PostgreSQL数据库
         ↓
    AI服务（向量搜索 + LLM生成）
```

**关键模块：**
- `routes/` - API路由（auth、articles、ai）
- `services/` - 业务逻辑（认证、校园认证）
- `repository/` - 数据访问层
- `utils/` - 工具类（Redis缓存）

**缓存策略：**
- 文章列表：三层缓存（today/page/detail），支持预缓存
- 文章详情：ETag缓存，3天过期
- AI对话历史：Redis存储，24小时TTL

#### 3. crawler - 数据爬取与处理管道

**技术栈：**
- Python 3.x
- requests（HTTP请求）
- OpenAI API（摘要生成、向量嵌入）

**核心功能：**
- **增量爬取**：按日期爬取OA通知，避免重复
- **AI摘要**：自动生成文章摘要
- **向量生成**：为文章生成向量嵌入
- **数据存储**：存储到PostgreSQL + pgvector

**数据流：**
```
定时任务 → 爬取OA列表 → 过滤新增文章
         ↓
    获取文章详情 → 生成AI摘要 → 生成向量嵌入
         ↓
    存储到PostgreSQL → 刷新Redis缓存
```

**关键模块：**
- `fetcher.py` - OA数据获取
- `summarizer.py` - AI摘要生成
- `embeddings.py` - 向量嵌入生成
- `pipeline.py` - 完整爬取流程
- `storage.py` - 数据存储

**运行时段控制：**
- 当天数据：仅在07:00-24:00运行
- 历史数据：随时可运行

## 🔄 完整数据流

### 1. 数据采集流程

```
定时任务触发
    ↓
Crawler爬取OA列表
    ↓
对比数据库，过滤新增文章
    ↓
获取文章详情（标题、正文、附件）
    ↓
调用AI服务生成摘要（带重试机制）
    ↓
调用嵌入服务生成向量
    ↓
生成向量嵌入
    ↓
存储到PostgreSQL（articles表 + vectors表）
    ↓
刷新Redis缓存（articles:today + articles:detail:{id}）
```

### 2. 用户查询流程

#### 文章列表查询

**首页加载当天所有文章：**
```
用户打开App
    ↓
请求 /api/articles/today
    ↓
检查Redis缓存（articles:today）
    ├─ 命中 → 返回缓存数据（带ETag）
    └─ 未命中 → 查询PostgreSQL（WHERE published_on = TODAY）
                  ↓
              存入Redis缓存（TTL=24h）
                  ↓
              返回数据（带ETag）
```

**滚动加载更旧文章：**
```
用户滑动到底部
    ↓
请求 /api/articles?before_id=81&limit=20
    ↓
检查Redis缓存（articles:page:81:20）
    ├─ 命中 → 返回缓存数据（带ETag）
    └─ 未命中 → 查询PostgreSQL（WHERE id < 81 ORDER BY id DESC LIMIT 20）
                  ↓
              存入Redis缓存（TTL=3天）
                  ↓
              异步预缓存下一页（articles:page:61:20）
                  ↓
              返回数据（带ETag）
```

#### AI智能搜索
```
用户输入问题："下学期奖学金申请什么时候开始？"
    ↓
请求 /api/ai/ask
    ↓
生成问题向量嵌入
    ↓
pgvector向量相似度搜索（余弦相似度）
    ↓
返回Top-K相关文章
    ↓
构建Prompt（系统提示 + 历史对话 + 相关文章）
    ↓
调用LLM生成回答
    ↓
返回回答 + 相关文章列表
    ↓
缓存对话历史到Redis（24小时TTL）
```

### 3. 推送通知流程

```
Crawler发现新文章
    ↓
存储到数据库
    ↓
触发推送任务
    ↓
通过Expo Push API发送通知
    ↓
用户设备接收通知
    ↓
用户点击通知 → 打开App → 查看文章详情
```

## 🚀 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- PostgreSQL 15+（支持pgvector扩展）
- Redis 7+

### 安装依赖

#### 后端
```bash
cd backend
cp env.example .env
# 配置.env文件中的数据库、Redis、AI服务等信息
uv sync
```

#### 爬虫
```bash
cd crawler
cp env.example .env
# 配置.env文件
uv sync
```

#### 客户端
```bash
cd OAP-app
npm install
cp .env.example .env
# 配置EXPO_PUBLIC_API_BASE_URL
```

### 启动服务

#### 启动后端API
```bash
cd backend
python app.py
# 服务运行在 http://localhost:4420
```

#### 运行爬虫
```bash
cd crawler
python main.py
# 或指定日期：python main.py --date 2024-01-01
```

#### 启动客户端
```bash
cd OAP-app
npm start
# 按提示选择平台（iOS/Android/Web）
```

## 📊 技术亮点

### 1. 智能缓存策略
- **三层缓存**：`articles:today`（24h）、`articles:page:{before_id}:{limit}`（3天）、`articles:detail:{id}`（3天）
- **ETag机制**：客户端可利用304 Not Modified减少网络传输
- **预缓存**：返回分页数据时异步缓存下一页，提高连续滑动命中率
- **客户端缓存**：AsyncStorage 本地存储

### 2. 向量搜索优化
- **pgvector集成**：高性能向量相似度搜索
- **时效性加权**：结合发布日期的混合评分算法
- **动态检索**：AI自动判断检索深度（brief/full）

### 3. AI对话增强
- **短期记忆**：Redis存储最近5轮对话，24小时TTL
- **工具调用**：LangGraph实现自主决策是否检索
- **个性化**：支持用户名，提供更自然的对话体验

### 4. 高可用设计
- **重试机制**：AI摘要生成失败自动重试（最多3次）
- **降级策略**：Redis不可用时仍可正常使用
- **限流保护**：Flask-Limiter防止API滥用

## 📝 API文档

详细的API文档请参考 [`docs/api_documentation.md`](docs/api_documentation.md)

### 主要端点概览

- **认证**：`POST /api/auth/token`、`POST /api/auth/token/refresh`、`POST /api/auth/logout`、`GET /api/auth/me`
- **文章**：`GET /api/articles/today`、`GET /api/articles?before_id={id}&limit={n}`、`GET /api/articles/{id}`
- **AI**：`POST /api/ai/ask`、`POST /api/ai/clear_memory`、`POST /api/ai/embed`

## 🔧 配置说明

详细的环境变量配置说明请参考 [`docs/configuration.md`](docs/configuration.md)

### 配置文件位置

- **后端**：`backend/.env`（模板：`backend/env.example`）
- **爬虫**：`crawler/.env`（模板：`crawler/env.example`）
- **客户端**：`OAP-app/.env`（模板：`OAP-app/.env.example`）

### 核心配置项

- 数据库连接（PostgreSQL + pgvector）
- Redis缓存配置
- JWT认证密钥
- AI服务配置（OpenAI兼容API）
- 嵌入服务配置

## 🧪 测试

### 后端测试
```bash
cd backend
uv run pytest
```

### 代码检查
```bash
cd backend
uv run ruff check .
```

### 客户端Lint
```bash
cd OAP-app
npm run lint
```

## 📦 部署

详细的部署指南请参考 [`docs/deployment.md`](docs/deployment.md)

### 快速部署

**后端（Docker，推荐分层 env）：**
```bash
# 1) 准备配置文件
cp env/common.env.example env/common.env
cp env/dev.env.example env/dev.env
cp env/prod.env.example env/prod.env

# 2) 启动 dev
./scripts/compose-up.sh dev

# 3) 启动 prod（可并行）
./scripts/compose-up.sh prod

# 4) 停止指定环境
./scripts/compose-down.sh dev
./scripts/compose-down.sh prod
```

**客户端（EAS Build）：**
```bash
cd OAP-app
eas build --platform ios    # iOS
eas build --platform android  # Android
```

### 部署文档

- [`docs/deployment.md`](docs/deployment.md) - 完整部署指南（Docker、传统部署、EAS Build）
- [`docs/eas_build.md`](docs/eas_build.md) - EAS构建详细说明

## 📄 许可证

**版权所有 © 2024 [24计科黄应辉](https://github.com/HandyWote)、[24大数据陈子俊](https://github.com/MEO-wj)

本项目采用非商业许可证。仅作者本人拥有商业使用权利，其他用户仅可用于学习、研究和个人非商业用途。

### 使用限制

- ✅ **允许**：学习、研究、个人非商业使用
- ✅ **允许**：修改代码用于学习目的
- ✅ **允许**：在非商业项目中引用本项目
- ❌ **禁止**：未经授权的商业使用
- ❌ **禁止**：将本项目或其修改版本用于商业产品或服务
- ❌ **禁止**：未经许可的分发或销售

### 联系方式

>handy@handywote.top

如需商业使用授权，请联系作者获取许可。
---



如有问题或建议，欢迎提交Issue。
