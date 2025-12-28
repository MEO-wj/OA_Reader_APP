# 开发计划（后端 / 爬虫 / APP）

## 概览
- 目标：用增量爬虫 + 后端 API + Expo RN APP 实现 OA 当日文章的抓取、摘要、通知和问答。
- 调度：外部 cron 每小时触发；`--date` 可补抓历史。
- 数据流：爬虫抓当日 → AI 摘要 → 入库（文章+附件元数据+当日向量）→ 后端 API 提供分页查询/问答 → APP 滚动加载 + 本地通知。

## 当前完成情况（基于代码核对）
- ✅ 爬虫：增量爬取、详情解析与附件元数据、AI 摘要（重试）、入库、向量生成、Redis 缓存刷新
- ✅ 后端：认证（账号密码 + 校园认证校验）、文章接口（分页 + 预缓存）、AI 问答/向量、ETag/304、限流
- ✅ APP：登录、首页列表/详情（滚动加载更多）、AI 助手（引用/高亮/Markdown/Mermaid）、通知管理（Android）、个人中心
- ✅ Redis 缓存策略：三层缓存（today/page/detail）+ 预缓存
- ✅ Token 自动刷新：APP 前台活跃时自动调用 refresh 接口更新 access_token
- ⏳ 监控与结构化日志：待补

## 已弃用 / 不再实现
- SSO token 换 JWT（改为账号密码登录 + 校园认证校验）
- 代理模式问答（`/ai/ask/proxy`）
- 阅读状态同步接口（`/articles/read`）
- 通知测试接口（`/notifications/test`）
- 内置调度器（统一改为外部 cron）
- 旧版文章接口：`/articles?date=&since=`、`/articles/by-date/<date>`

## 后端（Flask + Postgres + Redis）
1) **数据模型**
   - 文章表：`id, title, unit, link (unique), published_on, content, summary, attachments (jsonb), created_at, updated_at`
   - 向量表：`id, article_id, embedding, published_on, created_at`（仅当日用于问答）
   - 用户表：`id, username, display_name, password_hash, password_algo, password_cost, roles, created_at, updated_at`

2) **API（新版）**
   - 鉴权：`POST /auth/token`（用户名/密码登录，校园认证校验）、`POST /auth/token/refresh`、`POST /auth/logout`、`GET /auth/me`
   - 文章：
     - `GET /articles/today` - 获取当天所有文章（首页）
     - `GET /articles?before_id={id}&limit={n}` - 分页加载更旧文章
     - `GET /articles/{id}` - 文章详情
   - AI：`POST /ai/ask`（官方模型，向量检索范围由后端配置控制：`AI_VECTOR_LIMIT_DAYS`/`AI_VECTOR_LIMIT_COUNT`）

3) **缓存策略**
   - **缓存键设计**：
     - `articles:today` - 当天所有文章，TTL 24h
     - `articles:page:{before_id}:{limit}` - 分页文章，TTL 3天
     - `articles:detail:{id}` - 文章详情，TTL 3天
   - **预缓存**：返回分页数据时异步缓存下一页，提高连续滑动命中率
   - **ETag/304**：所有文章接口支持 ETag，客户端可用 `If-None-Match` 获取 304

4) **安全/运维**
   - HTTPS、JWT 过期/刷新、CORS
   - 监控：爬虫成功率、接口延迟、轮询量、AI 调用量（后续计划）

## 爬虫（Python） ✅ 已完成
1) **调度**
   - 每小时运行；限定 07:00–24:00，其他时间不跑。参数化 `--date` 支持补抓。

2) **列表与增量**
   - 仅处理目标日（默认当天）发布日期的条目，不 break，全量扫描当天列表。
   - 去重：查数据库当日已存在 `link` 集合，存在则跳过，不再拉详情/摘要。

3) **详情解析**
   - 抽取正文、标题、发布单位、发布日期、链接。
   - 解析附件名称+下载 URL，保存到 `attachments` 字段（不下载），正文中追加附件信息。

4) **AI 摘要**
   - 首轮对新增条目全部调用；失败收集后统一重试（最多 3 轮）。仍失败写占位摘要并记日志。

5) **入库与向量**
   - 新文章写文章表；为当日内容生成向量写向量表（仅当日供问答），使用 OpenAI 兼容 embedding 接口，pgvector 默认 1024 维。

6) **Redis 缓存刷新**
   - `refresh_today_cache()` - 刷新 `articles:today` 缓存（包含所有当天文章）
   - `refresh_article_detail_cache()` - 刷新 `articles:detail:{id}` 缓存

7) **日志与指标**
   - 每轮打印列表条数/新增数/AI 成功/AI 重试后失败/向量写入数/耗时。

## APP（Expo React Native）
1) **基础栈**
   - `expo-router`, `expo-secure-store`, `expo-notifications`, `expo-background-fetch`, `expo-task-manager`, `react-native-webview`, `react-native-markdown-display`

2) **鉴权**
   - 登录页采用账号/密码输入表单（替代"开启今日阅读"CTA），后端签发 JWT；secure-store 保存 access/refresh（当前无自动刷新）

3) **数据与缓存**
   - 列表/详情通过后端 API；正文/附件元数据展示（附件不下载）
   - 未读状态：由客户端本地维护（后端不记录已读）
   - **滚动加载**：首页加载当天所有文章（`/articles/today`），滑动到底部加载更多（`/articles?before_id={id}&limit=20`）

4) **轮询与通知**
   - Android 后台轮询（08:00–24:00，每 2 小时 + 0–15 分钟抖动）
   - 前台支持下拉刷新

5) **AI 问答**
   - 官方模式：调用后端 `/ai/ask`，向量检索范围由后端配置控制（按条数或天数）

6) **AI 助手（问答 + 引用材料）**
   - 接口：使用 `POST /ai/ask` 获取非流式回答
   - 引用材料：默认折叠；展示标题 + 片段（正文优先，80 字）；点击进入文章详情（复用详情弹层）
   - 关键词高亮：前端从用户问题提取关键词并在片段中高亮（不引入分词库）
   - Markdown + Mermaid：前端渲染 Markdown；遇到 ```mermaid``` 片段用 WebView 渲染
   - 用户称呼：基于登录返回的 `display_name/username` + 本地时间段（上午/下午/晚上）
   - UI：严格对齐 `OAP-app/原型.html` 的 AI 助手区块（排版、色彩、间距、动效）

7) **体验**
   - 通知开关/静音时段、轮询间隔（受系统最小值限制）
   - 列表搜索/筛选可后续迭代

8) **个人中心展示**
   - 仅展示头像、姓名与 VIP 标识（不显示部门信息）

9) **设置页与通知（已确认）**
   - 页面标题固定"个人中心"，样式严格对齐 `OAP-app/原型.html` 的设置页区块
   - 头像：显示 `display_name` 首字；无则取 `username` 首字；再无显示 `?`。不做头像上传
   - 项目项：仅保留"通知管理"；"模型配置"不做
   - VIP：`is_vip=false` 不显示；`is_vip=true` 且未过期显示"VIP Access"；过期显示"已过期"
   - 退出登录：仅清理 token，同时关闭通知开关并停止轮询
   - 通知范围：Android 实现，iOS 暂不实现
   - 轮询策略：每天 08:00–24:00；每 2 小时轮询一次并加入 0–15 分钟随机抖动
   - 通知内容：使用 OA `summary`。新增条数 <= 2 时逐条通知；>= 3 时合并通知，正文拼 3 条摘要
   - 权限引导：开启开关先弹"是否前往设置"，确认后跳转系统设置授权
   - 本地存储：通知开关与轮询节流状态使用 `AsyncStorage`

## 重构方案（基于现有爬虫升级）

### 模块划分
1. **爬虫模块** (`spider/`)
   - `CrawlerScheduler`: 外部 cron 调度（07:00–24:00 每小时执行）
   - `OACrawler`: 增量爬虫（去重、附件解析）
   - `AttachmentParser`: 附件 DOM 解析
   - `IncrementalTracker`: 增量跟踪

2. **数据存储模块** (`storage/`)
   - `DatabaseManager`: PostgreSQL 操作（文章、向量、阅读状态、用户）
   - `RedisCache`: 缓存最新列表（ETag/Last-Modified）
   - `VectorStore`: 向量生成与检索（pgvector）

3. **后端 API 模块** (`backend/`)
   - Flask 应用，包含认证、文章、AI、通知蓝图
   - JWT 认证、限流、CORS、结构化日志

4. **AI 服务模块** (`ai/`)
   - `Summarizer`: 摘要生成（重试机制）
   - `EmbeddingGenerator`: 向量生成（OpenAI/本地）
   - `AIService`: 问答服务（官方模式；代理模式已弃用）

5. **监控模块** (`monitoring/`)
   - 爬虫成功率、接口延迟、轮询量、AI 调用量
   - JSON 结构化日志

### 数据流
调度器触发 → 爬虫抓取当日列表 → 去重检查 → 解析详情+附件 → AI 摘要生成 → 入库文章表 → 生成向量 → 刷新 Redis 缓存（today/detail） → 后端 API 提供服务（today + 分页 + 预缓存） → APP 滚动加载 → 触发本地通知

### 增量抓取逻辑
1. 外部 cron 每小时运行（07:00–24:00），`--date` 参数支持补抓
2. 全量扫描当天列表，过滤出目标日期的条目
3. 去重：查询数据库当日已存在的 `link` 集合，跳过已处理条目
4. 解析附件元数据（不下载文件）
5. AI 摘要生成：首轮全量调用，失败重试最多 3 轮
6. 入库文章表，生成向量（仅当日），刷新 Redis 缓存

### AI 摘要与向量化
- **摘要生成**: 使用配置的 AI 模型（如 GLM-4.5-flash），重试机制保障可靠性
- **向量生成**: 使用 OpenAI 或本地 embedding 模型，存储为 pgvector 格式
- **问答服务**: 基于向量的相似性检索，提供官方模式

### 路线图与时间估算
1. **阶段 1: 基础数据库与爬虫重构** (3 天) – 建立数据库，实现增量爬虫
2. **阶段 2: 后端 API 开发** (4 天) – 实现 Flask API 和认证
3. **阶段 3: AI 向量化与问答** (3 天) – 向量生成和问答端点
4. **阶段 4: 调度与监控** (2 天) – 调度器和监控集成
5. **阶段 5: 联调与测试** (2 天) – 端到端测试和优化

**总时间**: 约 14 个工作日（2.5 周）

### 技术栈
- **语言**: Python 3.10+
- **数据库**: PostgreSQL + pgvector
- **缓存**: Redis
- **后端**: Flask, psycopg, JWT
- **爬虫**: requests, BeautifulSoup
- **AI**: OpenAI API / 智谱 GLM / sentence-transformers
- **部署**: Docker, Docker Compose

### 风险与缓解
- OA 网站结构变更：可配置解析规则
- AI 服务不可用：降级为占位摘要
- 性能瓶颈：数据库索引、查询优化、缓存策略
- 安全性：输入验证、SQL 注入防护、API 密钥管理

## 未决/确认点
- 附件 DOM 解析规则你会提供；实现时按规则提取名称/URL
- ETag/304 需后端与客户端配合（已实现）
- 上线前联调：登录、滚动加载、通知跳转、AI 问答、离线/弱网测试

## 未来计划
- 监控与结构化日志：补充指标采集与结构化日志输出

---

# 待实现优化方案（2024-12）

## 问题1: AI 429错误与模型负载均衡

### 背景
当前AI请求使用单一API密钥和模型配置，高并发时容易触发429速率限制错误。

### 解决方案
实现**轮询式负载均衡 + 429错误自动重试**机制。

### 配置格式
```bash
# 多模型配置（JSON数组格式）
# 每个配置项包含 api_key、base_url 和可用的模型列表
AI_MODELS=[
  {
    "api_key": "sk-key1",
    "base_url": "https://api1.com/v1",
    "models": ["glm-4-flash", "glm-4-plus"]
  },
  {
    "api_key": "sk-key2",
    "base_url": "https://api2.com/v1",
    "models": ["qwen-max", "glm-4-flash"]
  }
]

# 启用负载均衡（默认true）
AI_ENABLE_LOAD_BALANCING=true
```

### 设计要点
- 负载均衡器将所有（api_key, model）组合展开进行轮询
- 保留 `@lru_cache` 缓存LangGraph结构
- 每次 `agent_node` 执行时动态获取LLM实例
- 检测到429错误时自动切换到下一个配置重试

### 实现文件
- `backend/config.py` - 添加JSON解析支持
- `backend/services/ai_load_balancer.py` - 新建负载均衡器
- `backend/routes/ai.py` - 重构 `_build_agent` 和 `agent_node`

---

## 问题2: AI请求消息队列

### 背景
当前AI请求直接同步处理，无并发控制，高并发时可能压垮后端。

### 解决方案
使用**内存队列**（`threading.Queue`）实现请求排队。

### 配置格式
```bash
# 启用AI请求队列（默认true）
AI_QUEUE_ENABLED=true

# 最大队列长度（默认20）
AI_QUEUE_MAX_SIZE=20

# 请求处理超时时间（秒，默认30）
AI_QUEUE_TIMEOUT=30
```

### 设计要点
- 队列满时直接返回503状态码，不阻塞
- 请求入队后阻塞等待处理结果
- 单独的工作线程在Flask app_context中处理队列
- 返回503时附带明确的错误信息供前端展示

### 实现文件
- `backend/config.py` - 添加队列配置
- `backend/services/ai_queue.py` - 新建队列处理器
- `backend/routes/ai.py` - 修改AI路由使用队列
- `OAP-app/services/ai.ts` - 根据HTTP状态码返回不同错误
- `OAP-app/hooks/use-ai-chat.ts` - 显示具体错误信息

---

## 问题3: 后台任务400错误

### 背景
移动端延迟测试使用 `/articles/?since=xxx` 格式，但后端 `/articles/` 端点要求 `before_id` 参数为必填，导致400错误。

### 解决方案
修改移动端请求，改用 `/articles/today` 端点。

### 修改内容
- `OAP-app/notifications/notification-task.ts` 第159行：普通后台任务
- `OAP-app/notifications/notification-task.ts` 第381行：延迟测试

---

## 问题4: Web端SEO优化（轻量级）

### 背景
Lighthouse检测显示Web端缺少页面标题和meta描述。

### 解决方案
修改 `OAP-app/app/_layout.web.tsx`，添加 `<Head>` 组件和SEO元数据。

### 实现内容
```typescript
import { Head } from 'expo-router';

// 在return中添加
<Head>
  <title>OA Reader - 校内OA通知助手</title>
  <meta name="description" content="实时获取校园OA系统通知，AI智能摘要，便捷查阅。支持文章搜索、AI问答、个性化推送。" />
  <meta name="keywords" content="OA,校园通知,OA助手,智能摘要,AI问答" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
</Head>
```

### 预期效果
- 搜索引擎正确识别页面标题
- 社交媒体分享显示预览信息
- SEO基础得分提升

### 修改文件
- `OAP-app/app/_layout.web.tsx`

---

## 实施优先级

| 阶段 | 问题 | 工作量 |
|------|------|--------|
| 第一阶段 | 问题3：后台任务400错误 | 15分钟 |
| 第二阶段 | 问题4：Web端SEO优化 | 15分钟 |
| 第三阶段 | 问题1+2：AI负载均衡+消息队列 | 4-5小时 |
| 第四阶段 | 问题4：Web端深度性能优化（Vite迁移） | 暂缓 |
