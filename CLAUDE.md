# CLAUDE.md

## Top Rules
!!!回复使用中文!!!
使用superpower skill指导开发
使用TDD开发模式(REG)
优先复用项目中已有的组件
除非我明确要你帮我 git commit 其他情况一律不许commit
如果存在多个方案优先输出未来技术债最少的方案

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OAP (智能校园OA助手) - 一款为学校OA系统打造的智能移动助手，提供AI摘要、智能搜索和推送通知功能。项目采用微服务架构，分为三个核心模块：

- **OAP-app**: React Native 多端客户端 (Expo 54)
- **backend**: Flask API 服务
- **crawler**: 数据爬取与处理管道

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

### Backend
```bash
cd backend
uv sync              # 安装依赖（使用 uv）
python app.py        # 启动服务 (http://localhost:4420)
uv run pytest        # 运行测试
uv run ruff check .  # 代码检查
```

### Crawler
```bash
cd crawler
uv sync
python main.py                    # 运行当天爬取
python main.py --date 2024-01-01  # 指定日期爬取
```

## Architecture

### Frontend Structure (OAP-app)
```
OAP-app/
├── app/                    # Expo Router 页面
│   ├── (tabs)/            # 底部标签页路由
│   ├── login.tsx          # 登录页
│   └── _layout.tsx       # 根布局
├── components/            # 可复用UI组件
├── hooks/                 # 自定义Hooks (useAiChat, useArticles等)
├── services/              # API服务层
└── storage/               # 本地数据持久化 (AsyncStorage)
```

### Backend Structure
```
backend/
├── routes/                # API路由 (auth, articles, ai)
├── services/              # 业务逻辑
├── repository/            # 数据访问层
├── models/                # 数据模型
├── middleware/            # 中间件
├── app.py                 # 应用入口
├── config.py              # 配置管理
└── db.py                  # 数据库连接
```

### Crawler Structure
```
crawler/
├── fetcher.py             # OA数据获取
├── summarizer.py          # AI摘要生成
├── embeddings.py          # 向量嵌入生成
├── pipeline.py            # 完整爬取流程
├── storage.py             # 数据存储
└── main.py                # 入口文件
```

## Key Technical Details

### Data Flow
1. **文章查询**: 请求 → Redis缓存 → PostgreSQL → 返回 (三层缓存: today/page/detail)
2. **AI搜索**: 问题 → 向量嵌入 → pgvector相似度搜索 → LLM生成回答 → 返回
3. **爬取流程**: 爬取列表 → 过滤新增 → 获取详情 → AI摘要 → 向量嵌入 → 存储

### Caching Strategy (Backend)
- `articles:today` - 24小时TTL
- `articles:page:{before_id}:{limit}` - 3天TTL
- `articles:detail:{id}` - 3天TTL
- AI对话历史: Redis存储，24小时TTL

### Environment Configuration
- 后端: `backend/.env` (参考 `backend/env.example`)
- 爬虫: `crawler/.env` (参考 `crawler/env.example`)
- 客户端: `OAP-app/.env` (参考 `OAP-app/.env.example`)

核心配置项：数据库连接(PostgreSQL+pgvector)、Redis缓存、JWT密钥、AI服务配置(OpenAI兼容API)

## Development Notes

- 后端使用 `uv` 作为包管理工具
- 前端使用 Expo Router 进行文件路由
- 数据库需支持 pgvector 扩展
- 爬虫运行时段：当天数据仅在07:00-24:00运行
