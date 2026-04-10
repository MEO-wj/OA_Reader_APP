# AI Agent Backend

AI Agent 后端 - 文档检索助手

## 项目概述

基于 AI Agent 架构的文档检索助手，通过技能系统和多层检索架构，提供智能对话、技能调用和信息检索服务。

## 核心能力

| 能力 | 描述 |
|------|------|
| **智能对话** | 基于用户画像和历史上下文的个性化对话 |
| **技能调用** | AI 按需加载技能，渐进式披露专业能力 |
| **文档检索** | 三层混合检索（向量 + 关键词 + Rerank） |
| **参考读取** | 按需读取技能参考资料 |
| **长期记忆** | 用户画像浓缩，跨会话记忆保持 |
| **SSE 流式** | Server-Sent Events 实时流式输出 |

---

## 架构设计

### 系统架构总览

```mermaid
flowchart TB
    subgraph Frontend["前端"]
        Web["Web 客户端"]
    end

    subgraph API["API Gateway (FastAPI)"]
        Gateway["API 网关"]
        QueueMgr["分层并发队列"]
    end

    subgraph Lanes["APIQueue 分层 Lane"]
        LLMQ["LLM Lane (并发=2)"]
        EBDQ["Embedding Lane (并发=6)"]
        RRQ["Rerank Lane (并发=2)"]
    end

    subgraph Core["核心模块"]
        SkillSys["技能系统"]
        Retrieval["检索系统"]
        Memory["记忆系统"]
        Conv["对话管理"]
    end

    subgraph DB["数据库"]
        Skills["skills"]
        Refs["skill_references"]
        Docs["articles"]
        Vectors["vectors"]
        Profiles["user_profiles"]
        ConvTable["conversations"]
        Sessions["conversation_sessions"]
    end

    subgraph External["外部服务"]
        OpenAI["OpenAI API"]
        EBD["Embedding API"]
        Rerank["Rerank API"]
    end

    Web -->|SSE| Gateway
    Gateway --> QueueMgr
    QueueMgr --> LLMQ
    QueueMgr --> EBDQ
    QueueMgr --> RRQ

    LLMQ --> SkillSys
    LLMQ --> Memory
    LLMQ --> Conv

    SkillSys --> Retrieval
    Retrieval --> DB

    LLMQ --> OpenAI
    EBDQ --> EBD
    RRQ --> Rerank

    Memory --> DB
    Conv --> DB
```

### 核心设计理念

| 理念 | 描述 |
|------|------|
| **渐进式披露** | AI 按需加载 Skill，避免上下文污染 |
| **分层并发** | 所有外部请求通过 APIQueue 分 lane Semaphore 控制 |
| **Skill 数据库化** | Skill 定义存数据库，支持动态管理 |
| **记忆浓缩** | 短期对话 + 用户画像 → AI 浓缩 → 更新画像 |

### 依赖注入入口

- CLI 同步入口使用 `src.di.providers.get_chat_client()`
- API SSE 服务使用 `src.di.providers.get_chat_service()`
- 异步聊天客户端创建使用 `src.di.providers.create_chat_client()`
- `ChatClient` 内部继续通过 `get_skill_system()`、`get_memory_manager()`、`get_history_manager()` 收口依赖

---

## 核心模块

### 渐进式披露机制

AI 在初始化时只知道 Skill 的列表，不包含具体内容。当 AI 判断需要使用某个 Skill 时，才动态加载该 Skill 的 SKILL.md 和二级工具。

```mermaid
sequenceDiagram
    participant User as 用户
    participant Frontend as 前端
    participant API as FastAPI
    participant Client as ChatClient
    participant AI as OpenAI API
    participant DB as 数据库

    User->>Frontend: 发起对话
    Frontend->>API: POST /chat {user_id, message}
    API->>Client: ChatService.chat_stream()

    Note over Client: 初始化对话上下文
    Client->>DB: 查询用户画像
    Client->>DB: 查询对话历史

    Client->>AI: 发送请求<br/>System: Skill列表<br/>Tools: 基础工具（无二级工具）

    AI->>AI: 判断需要调用 article-retrieval 技能
    AI-->>Client: 返回: call article-retrieval

    Note over Client: Skill 激活
    Client->>DB: 加载 SKILL.md
    Client->>DB: 加载二级工具定义

    Client->>AI: 继续对话<br/>新增: Skill内容 + 二级工具

    AI->>AI: 使用 search_articles 工具
    AI-->>Client: 返回: call search_articles

    Client->>DB: 执行检索

    Client->>AI: 返回检索结果

    AI-->>Client: 返回最终回答

    Client->>API: 通过 SSE 推送响应
    API-->>Frontend: SSE 流式返回
    Frontend-->>User: 显示回答
```

### 技能系统

| 组件 | 描述 | 状态 |
|------|------|------|
| **Skill 加载 (文件系统)** | 从 skills/ 目录加载 Skill 定义 | ✅ 已实现（已废弃） |
| **Skill 加载 (数据库)** | 从数据库加载 Skill 定义 | ✅ 已实现（推荐） |
| **二级工具** | Skill 专属工具，激活后可用 | ✅ 已实现 |
| **read_reference** | AI 按需读取 Skill 参考资料 | ✅ 已实现 |
| **数据库化** | Skill 存数据库而非文件系统 | ✅ 已实现 |

### 检索系统

基于 Skill 的二级工具机制，提供多种检索能力：

| 工具 | 描述 | 状态 |
|------|------|------|
| `search_articles` | 向量搜索相关文章 | ✅ 已实现 |
| `grep_article` | 获取指定文章内容，支持多种搜索模式 | ✅ 已实现 |
| `grep_articles` | 跨多个文章搜索 | ✅ 已实现 |

#### grep_article 多模式搜索

`grep_article` 工具内部采用三层混合检索策略：

```
Layer 1: EBD 向量搜索 (top-20)
    ↓
Layer 2: 关键词模糊搜索 (top-20)
    ↓
Layer 3: Rerank 重排序 (top-k)
```

支持的搜索模式：`auto` / `summary` / `keyword` / `regex` / `section` / `line_range`

## 检索功能

### 通用文档检索
- 三层混合检索策略（向量 + 关键词 + Rerank）
- 支持多模式内容定位（summary/keyword/regex/section/line_range）

### 记忆系统

```
┌─────────────────────────────────────────────────────────────┐
│                        记忆系统                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  短期记忆                           长期记忆                 │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │ 对话历史        │  浓缩更新     │   用户画像       │     │
│  │ - 消息内容      │  ──────────►  │   - portrait_text│     │
│  │ - 对话评分      │    (AI API)   │   - knowledge_text│    │
│  │ - 时间戳        │               │   - preferences  │     │
│  └─────────────────┘               └─────────────────┘     │
│         ▲                                  │               │
│         │                                  ▼               │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │ 每条对话        │               │ 对话初始化时     │     │
│  │ 打分存储        │               │ 加载画像上下文   │     │
│  └─────────────────┘               └─────────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 分层并发队列 (APIQueue)

APIQueue 采用 asyncio.Semaphore 分 lane 控制并发：

| Lane | 并发数 | 用途 |
|------|--------|------|
| `llm` | 2 | 对话请求、AI 调用 |
| `embedding` | 6 | 向量生成 |
| `rerank` | 2 | 检索重排序 |

---

## 数据库设计

```mermaid
erDiagram
    articles ||--o{ vectors : "拥有"
    skills ||--o{ skill_references : "包含"
    user_profiles ||--o{ conversations : "拥有"
    user_profiles ||--o{ conversation_sessions : "拥有"
    conversations ||--|| conversation_sessions : "对应"

    articles {
        bigint id PK
        text title
        text unit
        text link UK
        date published_on
        text content
        text summary
        jsonb attachments
        timestamptz created_at
        timestamptz updated_at
    }

    vectors {
        bigint id PK
        bigint article_id FK
        vector embedding "vector(1024)"
        date published_on
        timestamptz created_at
        timestamptz updated_at
    }

    skills {
        int id PK
        varchar name UK
        text description
        varchar verification_token
        jsonb metadata
        text content
        text tools
        boolean is_static
        timestamptz created_at
        timestamptz updated_at
    }

    skill_references {
        int id PK
        int skill_id FK
        varchar file_path
        text content
        timestamptz created_at
    }

    user_profiles {
        int id PK
        uuid user_id UK
        text portrait_text
        text knowledge_text
        jsonb preferences
        timestamptz created_at
        timestamptz updated_at
    }

    conversations {
        int id PK
        uuid user_id
        varchar conversation_id
        varchar title
        jsonb messages
        timestamptz created_at
        timestamptz updated_at
    }

    conversation_sessions {
        int id PK
        uuid user_id
        varchar conversation_id
        varchar title
        timestamptz created_at
        timestamptz updated_at
    }
```

| 表名 | 用途 | 更新方式 |
|------|------|---------|
| `articles` | OA 文章元数据和内容 | crawler 爬取导入 |
| `vectors` | 文章向量嵌入 | crawler 生成导入 |
| `skills` | 技能定义 | 指导型: migration 初始化<br/>可更新型: CRUD 接口 |
| `skill_references` | 技能参考资料 | 与 skills 同步 |
| `user_profiles` | 用户画像（长期记忆） | AI 浓缩自动更新 |
| `conversations` | 对话记录（短期记忆） | 自动创建，JSONB 存储 |
| `conversation_sessions` | 会话元信息 | 自动创建 |

---

## 部署架构

```mermaid
flowchart TB
    subgraph Docker["Docker Compose"]
        API["FastAPI<br/>API Gateway"]
    end

    subgraph ExternalDB["外部数据库"]
        PG["PostgreSQL<br/>+ pgvector + pg_trgm<br/>(由 Docker Compose postgres 管理)"]
    end

    subgraph External["外部服务"]
        OpenAI["OpenAI API"]
        EBD["Embedding API"]
        Rerank["Rerank API"]
    end

    API --> PG
    API --> OpenAI
    API --> EBD
    API --> Rerank
```

> 注意：PostgreSQL 数据库由 Docker Compose 中的 postgres 容器管理，AI End 通过 `.env` 配置连接。

| 服务 | 技术栈 | 职责 |
|------|--------|------|
| **API Gateway** | FastAPI + Uvicorn | 接收请求、SSE 推送、分层并发控制 |
| **PostgreSQL** | PostgreSQL + pgvector + pg_trgm | 持久化存储、向量搜索 |

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 框架 | FastAPI + Uvicorn |
| 数据库 | PostgreSQL + pgvector + pg_trgm + asyncpg |
| 并发 | asyncio.Semaphore (APIQueue) |
| 部署 | Docker + Docker Compose |
| LLM | OpenAI API (Function Calling) |
| Embedding | BAAI/bge-m3 |
| Rerank | BAAI/bge-reranker-v2-m3 |

---

## 架构细节

以下组件架构图详细展示系统内部关键实现细节。

### 1. 异步队列与并发治理

APIQueue 采用**分层 lane** 机制，按 API 类型独立控制并发：

```mermaid
flowchart TB
    subgraph APIQueue["APIQueue 分层队列"]
        Queue["asyncio.Queue"]

        subgraph LLM["LLM Lane (并发=2)"]
            L1["Worker 1"]
            L2["Worker 2"]
            LLM_Sem["Semaphore(2)"]
        end

        subgraph EBD["Embedding Lane (并发=6)"]
            E1["Worker 1"]
            E2["Worker 2"]
            E3["Worker 3"]
            E4["Worker 4"]
            E5["Worker 5"]
            E6["Worker 6"]
            EBD_Sem["Semaphore(6)"]
        end

        subgraph RR["Rerank Lane (并发=2)"]
            R1["Worker 1"]
            R2["Worker 2"]
            RR_Sem["Semaphore(2)"]
        end

        Queue --> LLM_Sem
        Queue --> EBD_Sem
        Queue --> RR_Sem

        LLM_Sem --> L1 & L2
        EBD_Sem --> E1 & E2 & E3 & E4 & E5 & E6
        RR_Sem --> R1 & R2
    end
```

| Lane | 并发数 | 用途 |
|------|--------|------|
| `llm` | 2 | 对话请求、AI 调用 |
| `embedding` | 6 | 向量生成 |
| `rerank` | 2 | 检索重排序 |

---

### 2. 后台工具调用事件循环

工具调用通过**独立后台线程**的事件循环执行：

```mermaid
sequenceDiagram
    participant Main as 主线程 (chat)
    participant Handler as handle_tool_calls_sync
    participant BgLoop as 后台事件循环
    participant Tool as 二级工具函数

    Main->>Handler: handle_tool_calls_sync(tool_calls)
    Handler->>BgLoop: run_coroutine_threadsafe
    Note over BgLoop: 独立线程<br/>asyncio.new_event_loop()
    BgLoop->>Tool: await _dispatch_secondary_tool()
    Tool-->>BgLoop: JSON 结果
    BgLoop-->>Handler: future.result()
    Handler-->>Main: tool_messages[]
```

**关键特性**：
- 主线程同步，后台线程异步执行
- `run_coroutine_threadsafe` 跨线程调度
- 生命周期：`_get_tool_loop()` 创建 → `shutdown_tool_loop()` 关闭

---

### 3. grep_article 多模式搜索流程

`grep_article` 内部采用**策略模式**匹配不同搜索模式：

```mermaid
flowchart TB
    Input["grep_article() 调用"] --> DetectMode{mode 参数}

    DetectMode -->|auto| AutoMode["_detect_mode()"]
    DetectMode -->|指定模式| UseMode["使用指定模式"]

    AutoMode --> CheckPattern{有 pattern?}
    CheckPattern -->|是| RegexMode["regex"]
    CheckPattern -->|否| CheckStart{有 start_line?}
    CheckStart -->|是| LineRangeMode["line_range"]
    CheckStart -->|否| CheckSection{有 section?}
    CheckSection -->|是| SectionMode["section"]
    CheckSection -->|否| CheckKeyword{有 keyword?}
    CheckKeyword -->|是| KeywordMode["keyword"]
    CheckKeyword -->|否| SummaryMode["summary"]

    UseMode --> CheckSummary{是 summary?}
    CheckSummary -->|是| SummaryMode
    CheckSummary -->|否| GetMatcher["_get_matcher(mode)"]

    SummaryMode --> ReturnSummary["返回文档摘要"]

    GetMatcher --> IsKeyword{是 keyword?}
    IsKeyword -->|是| SplitKeyword["_split_keyword_terms()"]
    IsKeyword -->|否| DirectMatch["直接调用 matcher.match()"]

    SplitKeyword --> CheckMulti{多个关键词?}
    CheckMulti -->|是| OrMatch["_match_keyword_or()"]
    CheckMulti -->|否| DirectMatch

    OrMatch --> HasResults{有结果?}
    HasResults -->|是| Success["返回匹配结果"]
    HasResults -->|否| RegexFallback["Regex 回退匹配"]

    RegexFallback --> FallbackResult{有结果?}
    FallbackResult -->|是| Success
    FallbackResult -->|否| NotFound["返回未找到"]

    DirectMatch --> CheckDirect{有结果?}
    CheckDirect -->|是| Success
    CheckDirect -->|否| NotFound

    ReturnSummary --> Output["统一输出格式"]
    Success --> Output
    NotFound --> Output

    Output["ResultFormatter"]
```

---

### 4. 文章检索器继承体系

所有文章检索能力由 `ArticleRetriever` 实现，继承自 `BaseRetriever` 基类：

```mermaid
classDiagram
    class BaseRetriever {
        <<abstract>>
        #table_name: str
        #select_columns: list
        #_vector_search()
        #_rerank()
        #_build_metadata_filter()*
    }

    class ArticleRetriever {
        +search_articles(query, keywords, top_k)
        +grep_article(article_id, mode, ...)
        +grep_articles(article_ids, mode, ...)
        +_build_metadata_filter()
    }

    BaseRetriever <|-- ArticleRetriever
```

| 检索器 | 表名 | 特点 |
|--------|------|------|
| `ArticleRetriever` | `articles` | 三层混合检索（向量+关键词+Rerank）+ 多模式内容定位 |

---

### 5. 通用内容处理工具 (document_content)

```mermaid
classDiagram
    class Matcher {
        <<abstract>>
        +match(content, **kwargs) MatchResult[]
    }

    class KeywordMatcher {
        +match(content, keyword, context_lines, max_results)
    }

    class RegexMatcher {
        +match(content, pattern, context_lines)
    }

    class SectionMatcher {
        +match(content, section)
    }

    class LineRangeMatcher {
        +match(content, start_line, end_line)
    }

    class MatchResult {
        +content: str
        +line_number: int
        +context_before: str[]
        +context_after: str[]
        +highlight_ranges: (int,int)[]
    }

    class ContentFetcher {
        -_cache: dict
        +get(id) tuple(str,str)
    }

    class ResultFormatter {
        +success(data, metadata) dict
        +not_found(reason) dict
        +error(message) dict
    }

    Matcher <|-- KeywordMatcher
    Matcher <|-- RegexMatcher
    Matcher <|-- SectionMatcher
    Matcher <|-- LineRangeMatcher
    Matcher --> MatchResult
```

**使用状态**：

| 功能 | 使用工具 |
|------|----------|
| `grep_article` | 复用 Matcher 策略 |
| `search_articles` | 统一文章检索入口 |

---

### 6. 技能系统两级工具机制

AI 按需激活技能，动态加载二级工具：

```mermaid
stateDiagram-v2
    [*] --> 初始化: 启动

    初始化 --> 一级工具: 构建工具定义
    一级工具: 仅技能列表<br/>无二级工具

    state 一级工具 {
        [*] --> 技能列表
        技能列表: article-retrieval<br/>read_reference
    }

    一级工具 --> 技能已激活: AI 调用技能
    技能已激活: 加入 activated_skills

    技能已激活 --> 二级工具可用: 重建工具定义

    state 二级工具可用 {
        [*] --> 全部工具
        全部工具: 一级工具 +<br/>search_articles<br/>grep_article<br/>grep_articles<br/>read_reference<br/>form_memory
    }

    二级工具可用 --> 执行二级工具: AI 调用
    执行二级工具 --> 二级工具可用: 返回结果
```

---

### 7. 主程序流程

```mermaid
flowchart TB
    Start([启动 main.py]) --> LoadConfig[Config.load 从环境变量加载]
    LoadConfig --> CreateClient[创建 ChatClient]
    CreateClient --> InitSkills[DbSkillSystem 从数据库加载技能]
    InitSkills --> ShowBanner[显示欢迎信息]
    ShowBanner --> MainLoop[主循环]

    MainLoop --> GetInput[获取用户输入]
    GetInput --> CheckQuit{退出命令?}
    CheckQuit -->|quit/exit/q| PrintUsage[打印 Token 使用统计]
    PrintUsage --> CloseClient[client.close 关闭资源]
    CloseClient --> End([结束])

    CheckQuit -->|否| CheckList{skills/list?}
    CheckList -->|是| ListSkills[显示技能列表]
    ListSkills --> MainLoop

    CheckList -->|否| CheckVerify{verify 命令?}
    CheckVerify -->|是| ShowToken[显示验证暗号]
    ShowToken --> MainLoop

    CheckVerify -->|否| ChatCall[client.chat 调用]
    ChatCall --> CheckToken{包含验证暗号?}
    CheckToken -->|是| PrintSuccess[验证成功提示]
    CheckToken -->|否| PrintResponse[打印 AI 回复]
    PrintSuccess --> PrintResponse
    PrintResponse --> MainLoop
```

**命令类型**：
- `quit/exit/q` - 退出程序
- `skills/list` - 查看技能列表
- `verify <skill_name>` - 显示验证暗号
- 其他 - 与 AI 对话

---

### 8. 数据导入脚本流程

```mermaid
flowchart TB
    Start([运行 import_skills.py]) --> ScanDir[扫描 skills/ 目录]
    ScanDir --> ReadFiles[读取 SKILL.md / TOOLS.md / 参考文件]
    ReadFiles --> ComputeHash[hash_text 计算内容哈希]
    ComputeHash --> QueryDB{查询数据库}
    QueryDB --> CheckExists{已存在且无变更?}
    CheckExists -->|是| Skip[跳过]
    CheckExists -->|否| Import[导入处理]

    Import --> UpsertSkill[UPSERT skills 表]
    UpsertSkill --> UpsertRefs[UPSERT skill_references 表]
    UpsertRefs --> Next{还有文件?}
    Skip --> Next
    Next -->|是| Import
    Next -->|否| PrintStats[打印导入统计]
    PrintStats --> End([结束])
```

**支持的导入脚本**：
- `scripts/import_skills.py` — 技能定义导入（SKILL.md, TOOLS.md, 参考文件）

---

## 架构演进

| 方面 | 旧版本 (Flask) | 当前版本 (FastAPI + 技能系统) |
|------|----------------|----------------|
| **框架** | Flask + LangGraph | FastAPI + 技能系统 |
| **交互方式** | JSON API | SSE 流式 + JSON 兼容 |
| **Skill 存储** | 文件系统 | 数据库 (DbSkillSystem) |
| **并发处理** | 同步队列 | asyncio.Semaphore 分 lane |
| **用户管理** | 无 | 用户系统 + 画像 + 会话 |
| **记忆管理** | Redis 缓存 | PostgreSQL 短期 + 长期记忆 |
| **部署方式** | 本地运行 | Docker 容器化 |
