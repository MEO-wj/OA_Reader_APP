# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 提供在此代码库中工作的指导。

## Top Rules
!!!回复使用中文!!!
使用superpower skill指导开发
使用TDD开发模式
优先复用项目中已有的组件
除非我明确要你帮我 git commit 其他情况一律不许commit
如果存在多个方案优先输出未来技术债最少的方案


## 项目概述

通用 AI Agent 后端 - 基于技能系统的 AI 服务，提供 CLI 交互和 FastAPI API 两种运行模式，使用 OpenAI Function Calling 技术动态调用技能。

### 核心特性

- **技能系统**: 从数据库或文件系统动态加载技能定义 (SKILL.md)
- **验证暗号**: 每个技能包含唯一暗号，用于验证 AI 真实使用了技能
- **三层检索**: 向量搜索 + 关键词搜索 + Rerank 重排序
- **记忆系统**: 用户画像 (长期记忆) + 对话历史 (短期记忆)
- **SSE 流式**: 新 /chat 接口支持 Server-Sent Events 流式输出
- **旧接口兼容**: /ask、/clear_memory、/embed 兼容旧 AI End 协议
- **分层架构**: 代码按职责分层 (config/core/chat/api/di/db/ui)

## 架构

```
src/
├── config/              # 配置管理
│   └── settings.py          # 从环境变量加载配置 (dataclass, frozen)
├── core/                # 核心业务逻辑
│   ├── skill_parser.py      # 解析 SKILL.md (YAML front matter)
│   ├── skill_system.py      # 文件系统版技能系统 (已废弃，请用 DbSkillSystem)
│   ├── db_skill_system.py   # 数据库版技能系统 (推荐)
│   ├── skill_adapter.py     # 统一技能适配层 (SkillBackend 枚举)
│   ├── tool_activation.py   # 工具激活策略 (read_reference 等)
│   ├── base_retrieval.py    # 检索基类 (embedding, 向量搜索)
│   ├── article_retrieval.py # OA 文章检索 (search_articles, grep_article, grep_articles)
│   ├── response_composer.py # 检索结果编排 (上下文块, 来源引用)
│   ├── document_content.py  # 文章内容获取与匹配 (策略模式)
│   ├── api_clients.py       # API 客户端 (LLM, Embedding, Rerank)
│   ├── api_queue.py         # 分层并发队列 (llm/embedding/rerank 分 lane)
│   ├── db.py                # 数据库连接池 (asyncpg)
│   └── hash_utils.py        # 哈希工具 (SHA256)
├── chat/                # 聊天功能
│   ├── client.py            # ChatClient 主聊天逻辑 (同步+异步)
│   ├── handlers.py          # 工具调用处理 (后台线程事件循环)
│   ├── context_truncator.py # 工具输出智能截断
│   ├── context_budget.py    # 上下文预算管理
│   ├── compact.py           # 对话历史压缩
│   ├── history_manager.py   # 历史管理 (加载、追加、标题生成)
│   ├── memory_manager.py    # 记忆管理 (画像形成与保存)
│   ├── prompts_runtime.py   # 运行时提示词模板
│   └── utils.py             # 工具函数
├── api/                 # FastAPI 路由层
│   ├── main.py              # 应用入口, lifespan, 路由注册
│   ├── admin.py             # 管理路由 (预留)
│   ├── chat_service.py      # SSE 流式聊天服务
│   ├── models.py            # 新版请求/响应模型
│   ├── compat_service.py    # 旧接口兼容层 (/ask, /clear_memory, /embed)
│   ├── compat_models.py     # 旧接口数据模型
│   ├── import_decider.py    # 自动导入决策
│   └── import_probe.py      # 导入探测
├── di/                  # 依赖注入
│   ├── container.py         # DI 容器
│   └── providers.py         # 服务提供者
├── db/                  # 数据访问层
│   └── memory.py            # 记忆系统数据库操作 (会话, 画像, async)
├── ui/                  # 用户界面
│   └── console.py           # CLI 终端彩色输出
├── config/__init__.py    # 导出 Config
├── chat/__init__.py      # 导出 ChatClient
└── ui/__init__.py        # 导出 Colors, 打印函数

skills/                   # 技能定义目录 (通过 import_skills.py 导入数据库)
└── article-retrieval/
    ├── SKILL.md           # 技能定义 (YAML front matter + 内容)
    └── TOOLS.md           # 工具定义

scripts/                  # 数据导入脚本
└── import_skills.py      # 技能文件导入数据库

migrations/               # 数据库迁移
├── 001_init_generic_backend.sql  # 基线迁移
├── migrate.py            # 迁移执行器
└── verify_table.py       # 表结构验证

main.py                   # CLI 交互入口
```

### 技能系统工作流

1. **扫描**: DbSkillSystem 从数据库加载技能定义（启动时通过 AUTO_IMPORT 从 skills/ 导入）
2. **解析**: 每个 SKILL.md 由 SkillParser 解析 YAML front matter + 内容
3. **适配**: SkillAdapter 统一封装文件系统/数据库两种后端
4. **工具定义**: 技能信息转换为 OpenAI Function Calling 格式
5. **激活**: AI 通过 Function Calling 调用技能，动态加载二级工具
6. **验证**: 检查 AI 回复是否包含技能的验证暗号

## 常用命令

### 构建与测试

```bash
# 安装依赖（使用 uv）
uv sync

# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/unit/test_skill_system.py -v

# 测试覆盖率
uv run pytest tests/ --cov=src --cov-report=term

# 跳过集成测试
uv run pytest -m "not integration"
```

### 运行程序

```bash
# API 模式 (FastAPI, 默认端口 4421)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 4421

# CLI 交互模式
uv run main.py
```

### 开发模式

- **TDD**: 所有新功能先写测试，再实现代码
- **分层**: 每个模块职责单一，高内聚低耦合
- **类型提示**: 使用 Python 3.11+ 类型标注
- **asyncio_mode = "auto"**: 测试无需手动 `@pytest.mark.asyncio`

## 添加新技能

1. 在 `skills/` 下创建新目录，如 `skills/new-skill/`
2. 创建 `SKILL.md` 文件，格式：

```markdown
---
name: new-skill
description: 技能描述
verification_token: UNIQUE-TOKEN-123
---

# 技能内容

详细说明技能的使用场景和指令。
```

3. 设置 `AUTO_IMPORT=true` 后重启 API 服务，技能会自动导入数据库

## 技能 SKILL.md 格式

每个技能目录包含一个 `SKILL.md` 文件，使用 YAML front matter 定义元数据：

```yaml
---
name: skill-name              # 技能唯一标识
description: 技能描述         # 简短描述
verification_token: TOKEN-XYZ    # 验证暗号（可选）
---
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/skills` | 列出可用技能 |
| POST | `/chat` | SSE 流式聊天 (新接口) |
| GET | `/chat/history` | 获取聊天历史 |
| GET | `/chat/sessions` | 列出用户会话 |
| POST | `/chat/sessions` | 创建新会话 |
| GET | `/chat/sessions/{id}` | 获取会话详情 |
| DELETE | `/chat/sessions/{id}` | 删除会话 |
| GET | `/chat/users` | 列出最近用户 |
| DELETE | `/chat/history` | 清空用户数据 |
| POST | `/ask` | 旧兼容问答接口 (JSON) |
| POST | `/clear_memory` | 旧兼容清除记忆 |
| POST | `/embed` | 旧兼容文本向量化 |

## 环境变量

| 变量 | 说明 | 默认值 |
|-------|------|--------|
| OPENAI_API_KEY | OpenAI API 密钥 | (必需) |
| OPENAI_BASE_URL | API 基础 URL | https://api.openai.com/v1 |
| OPENAI_MODEL | 使用的模型 | deepseek-v3.2 |
| SKILLS_DIR | 技能目录 | ./skills |
| DB_HOST | 数据库主机 | (必需) |
| DB_PORT | 数据库端口 | (必需) |
| DB_USER | 数据库用户 | (必需) |
| DB_PASSWORD | 数据库密码 | (必需) |
| DB_NAME | 数据库名 | (必需) |
| EMBEDDING_MODEL | Embedding 模型 | BAAI/bge-m3 |
| EMBEDDING_DIMENSIONS | 向量维度 | 1024 |
| EMBEDDING_API_KEY | Embedding API 密钥 | (继承 OPENAI_API_KEY) |
| EMBEDDING_BASE_URL | Embedding API 地址 | (继承 OPENAI_BASE_URL) |
| RERANK_MODEL | Rerank 模型 | BAAI/bge-reranker-v2-m3 |
| RERANK_MAX_CANDIDATES | Rerank 最大候选数 | 40 |
| RERANK_TIMEOUT | Rerank 超时 (秒) | 60.0 |
| RERANK_BASE_URL | Rerank API 地址 | (继承 OPENAI_BASE_URL) |
| RERANK_API_KEY | Rerank API 密钥 | (继承 OPENAI_API_KEY) |
| LLM_TIMEOUT | LLM 请求超时 (秒) | 120.0 |
| EMBEDDING_TIMEOUT | Embedding 请求超时 (秒) | 30.0 |
| LLM_MAX_TOKENS | LLM 最大 token 数 | 1500 |
| LLM_TEMPERATURE | LLM 温度参数 | 0.1 |
| AI_COMPAT_TZ | 兼容层时区 | (自动检测) |
| AUTO_MIGRATE | 启动时自动迁移 | false |
| AUTO_IMPORT | 启动时自动导入技能 | false |

## 特殊命令 (CLI 模式)

- `skills` 或 `list` - 列出所有可用技能
- `verify <skill_name>` - 显示特定技能的验证暗号
- `quit`, `exit`, `q` - 退出程序

## 注意事项

- **所有 Python 脚本请使用 uv 运行**
- **回复请使用中文**
- **不包含敏感信息** (API keys, tokens) 在代码或提交中

## 检索系统架构（三层策略）

数据模型采用 **articles + vectors 双表结构**：
- `articles`: 存储 OA 文章元数据（标题、单位、链接、发布日期、内容、摘要、附件）
- `vectors`: 存储向量嵌入，通过 `article_id` 外键关联 articles（ON DELETE CASCADE）

检索策略：
1. **Layer 1: EBD 向量搜索** - vectors JOIN articles 语义召回 top-20
2. **Layer 2: 关键词模糊搜索** - pg_trgm 精确匹配 articles 表，召回 top-20
3. **Layer 3: Rerank 重排序** - 使用 bge-reranker-v2-m3 模型重排序，返回 top-k

核心模块：
- `src/core/article_retrieval.py` — ArticleRetriever 继承 BaseRetriever，实现 search_articles、grep_article、grep_articles
- `src/core/response_composer.py` — ResponseComposer 编排上下文块和来源引用
- `src/core/base_retrieval.py` — BaseRetriever 提供 embedding 生成、向量搜索基类

## 数据库表

- `articles`: OA 文章表 (id, title, unit, link, published_on, content, summary, attachments, created_at, updated_at)
- `vectors`: 向量表 (id, article_id FK, embedding vector(1024), published_on, created_at, updated_at)
- `skills`: 技能定义表 (id, name, description, verification_token, metadata, content, tools, is_static, created_at, updated_at)
- `skill_references`: 技能参考资料表 (id, skill_id FK, file_path, content, created_at)
- `conversations`: 对话记录表 (id, user_id UUID, conversation_id, title, messages JSONB, created_at, updated_at)
- `conversation_sessions`: 会话元信息表 (id, user_id UUID, conversation_id, title, created_at, updated_at)
- `user_profiles`: 用户画像表 (id, user_id UUID, portrait_text, knowledge_text, preferences JSONB, created_at, updated_at)

## 并发治理与生命周期

- 采用**分层队列** (APIQueue) 而非单全局队列：`llm`、`embedding`、`rerank` 分 lane 通过 Semaphore 控制并发。
- 并发参数（默认）：
  - `LLM 并发`: 2
  - `Embedding 并发`: 6
  - `Rerank 并发`: 2
  - `搜索重试次数`: 2（总 3 次尝试）
  - `重试退避`: 50ms
- 关闭顺序：`close_clients` → `close_resources` → `close_pool` → `close_api_queue` → `shutdown_tool_loop`
- 常见排查命令：
  - `uv run pytest tests/integration/test_concurrency_regression.py -v`
  - `uv run pytest tests/unit/test_article_retrieval.py tests/unit/test_chat_client.py tests/unit/test_db.py -v`

---

## 开发经验总结

### read_reference 功能 (2026-02)

**问题**：AI 调用技能时，只能看到 SKILL.md 的指令内容，无法直接访问技能目录下的参考资料（references/）。

**解决方案**：
1. 新增 `read_reference` 工具，支持按需读取指定技能的 reference 文件
2. 修改系统提示词，明确调用顺序：先调用技能 → 再根据需要使用 read_reference
3. 添加 API 错误处理，当 API 返回空响应时显示友好提示

**关键代码位置**：
- `src/core/skill_system.py::read_reference()` - 读取 reference 文件
- `src/core/skill_system.py::build_tools_definition()` - 添加 read_reference 工具定义
- `src/chat/handlers.py::handle_tool_calls()` - 处理 read_reference 工具调用
- `src/chat/client.py::chat()` - API 错误处理和调试日志

**使用流程**：
```
用户提问 → AI 调用技能（获取 SKILL.md）→ AI 看到 references 路径
→ AI 调用 read_reference（读取具体文件）→ AI 基于文件内容回复
```

**测试覆盖**：
- `tests/unit/test_skill_system.py` - read_reference 功能测试
- `tests/unit/test_handlers.py` - 工具调用处理测试
- `tests/unit/test_chat_client.py` - API 错误处理测试

**经验教训**：
1. 工具描述必须清晰明确，避免 AI 误用（如直接调用 read_reference 而不先调用技能）
2. API 可能返回空响应，需要添加错误处理
3. 详细的调试日志有助于定位问题
4. 遵循 TDD 原则，先写测试再实现代码
