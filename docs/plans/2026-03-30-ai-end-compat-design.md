# AI End Refactor 兼容旧 ai_end 接口设计

## 背景

当前 `ai_end_refactor` 以 `/chat`（SSE）为主，而历史调用链路（尤其 backend 代理）依赖旧 `ai_end` 的 JSON 协议接口：`/ask`、`/clear_memory`、`/embed`。

本设计目标是在不修改 backend 代码的前提下，通过将 `AI_END_URL` 指向 `ai_end_refactor` 完成平滑切换，并保持旧接口语义稳定。

## 核心目标

1. `ai_end_refactor` 对外兼容旧 `ai_end` 公共接口，覆盖 `/ask`、`/clear_memory`、`/embed`。
2. backend 无需改代码，仅通过 `AI_END_URL` 切换完成迁移。
3. `/ask` 旧字段 `question`、`top_k`、`display_name`、`user_id` 全量适配。
4. `clear_memory` 语义改为创建新会话；`ask` 按当天最新会话 `conversation_id` 执行。
5. “当天”判定支持配置优先级：环境变量 > 配置字段 > PG 会话时区。
6. 对外响应保留旧字段，允许新增扩展字段。
7. `/ask` 强制返回单次 JSON（`application/json`），不得返回 SSE 或其他流式格式。
8. 不改现有健康检查接口行为，不将 `/health` 纳入本次兼容改造范围。

## 约束与边界

- 仅在 `ai_end_refactor` 内新增兼容层，不新增独立微服务。
- 不做服务内 HTTP 回环（不通过内部再次请求 `/chat`）。
- 兼容层复用现有 `MemoryDB`、`ChatClient`、检索与 embedding 能力。
- 额外未知入参字段静默忽略。

## 已确认行为口径

### 1. `/ask`

- `question` 必填；缺失返回：`{"error":"请求参数错误，缺少question字段"}`，HTTP 400。
- `user_id` 可选：
  - 传入时启用会话选择逻辑。
  - 未传时请求仍可执行，且响应中不返回 `conversation_id`、不返回 `session_created`。
- `top_k` 规则：
  - 仅在合法值时进入运行时提示。
  - 空值或非法值与未传一致，不向 LLM 注入 `top_k` 提示。
- `display_name` 规则：
  - 传入后注入运行时提示（可酌情称呼，不强制）。
- 成功响应至少包含旧字段：`answer`、`related_articles`。
- 有 `user_id` 时附加扩展字段：`conversation_id`、`session_created`。
- 响应 `Content-Type` 必须是 `application/json`。

### 2. `/clear_memory`

- `user_id` 必填；缺失返回：`{"error":"用户信息缺失"}`，HTTP 400。
- 新语义：不删除历史会话，创建新 `conversation_id` 作为新会话。
- 成功返回：`{"cleared": true, "conversation_id": "..."}`，HTTP 200。

### 3. `/embed`

- `text` 必填；缺失返回：`{"error":"请求参数错误，缺少text字段"}`，HTTP 400。
- 成功返回：`{"embedding":[...]}`，HTTP 200。
- 失败语义与旧版一致，优先返回可恢复错误，未知异常返回统一错误。

### 4. `/health`

- 本次不做兼容改造，不修改现有健康检查接口行为。

## 架构设计

### 1. 兼容 API 路由层（新增）

新增 3 个兼容入口：

- `POST /ask`
- `POST /clear_memory`
- `POST /embed`

职责：

- 参数校验与错误文案对齐
- 响应字段裁剪（旧字段优先、扩展字段按规则输出）
- 响应类型固定（`application/json`）

### 2. 兼容编排层（新增）

新增 `CompatService`（命名可调整）封装兼容流程：

- 解析有效时区
- 计算“当天”范围
- 选择或创建会话
- 组装运行时提示（`top_k`、`display_name`）
- 调用 `ChatClient` 并聚合为单次 JSON
- 输出兼容响应

### 3. 复用能力层（保持）

- 会话与记忆：`src/db/memory.py`
- 问答执行：`src/chat/client.py`
- 检索与工具：`src/core/article_retrieval.py` 及现有 skill 调用链
- 向量生成：`src/core/base_retrieval.py` 的 `generate_embedding`

## 关键数据流

### 1. `/ask` 数据流

1. 校验 `question`。
2. 读取 `top_k`、`display_name`、`user_id`（未知字段忽略）。
3. 若存在 `user_id`：
   - 解析有效时区。
   - 按时区计算“今天”起止。
   - 查询该用户今天 `created_at` 最新会话。
   - 若无会话则创建新会话，并置 `session_created=true`；否则 `false`。
4. 组装运行时提示：
   - `top_k` 合法时写入检索建议提示。
   - `display_name` 写入可选称呼提示。
5. 调用 `ChatClient` 执行问答，消费内部事件流并聚合：
   - 生成最终 `answer`
   - 从工具结果中提取并格式化 `related_articles`
6. 输出单个 JSON：
   - 必含旧字段 `answer`、`related_articles`
   - 有 `user_id` 时附加 `conversation_id`、`session_created`
7. 强制响应 `application/json`。

### 2. `/clear_memory` 数据流

1. 校验 `user_id`。
2. 创建新会话并生成新 `conversation_id`。
3. 返回 `cleared=true` + `conversation_id`。

## 时区策略设计

有效时区优先级：

1. 环境变量 `AI_COMPAT_TZ`
2. 配置字段 `ai_compat_timezone`
3. 数据库 `SHOW TIMEZONE`

实现要求：

- 当天判定统一基于“有效时区”。
- 与 PG 语义一致，避免跨时区误取会话。

## 字段契约

### `/ask` 请求

- 必填：`question`
- 可选：`top_k`、`display_name`、`user_id`
- 未知字段：忽略

### `/ask` 响应

- 必有：`answer`、`related_articles`
- 条件扩展：
  - 有 `user_id`：返回 `conversation_id`、`session_created`
  - 无 `user_id`：省略这两个扩展字段

### `/clear_memory` 响应

- 旧字段：`cleared`
- 扩展字段：`conversation_id`

## 错误语义与状态码

- `/ask` 缺 `question`：400 + `请求参数错误，缺少question字段`
- `/clear_memory` 缺 `user_id`：400 + `用户信息缺失`
- `/embed` 缺 `text`：400 + `请求参数错误，缺少text字段`

## 测试与验收

### 1. 新增兼容契约测试

覆盖：

1. `/ask` 参数校验、JSON 响应类型、扩展字段显隐规则。
2. `/ask` 对 `top_k` 非法值按未提供处理。
3. `/clear_memory` 新语义与返回字段。
4. `/embed` 参数校验与成功输出。

### 2. 新增时区与会话测试

覆盖：

1. 时区优先级解析。
2. 当天最新会话复用。
3. 当天无会话时新建会话与 `session_created` 标志。

### 3. 非回归测试

- 保证现有 `/chat` SSE 行为不被破坏。
- 保证现有 unit/integration 关键路径仍通过。

### 4. 验收标准（DoD）

1. backend 不改代码，仅改 `AI_END_URL` 可联通。
2. `/ask` 固定返回 `application/json`，不返回 SSE。
3. 三条旧错误文案严格对齐。
4. 旧字段稳定，扩展字段符合显隐规则。
5. 兼容契约测试与回归测试通过。

## 文件影响（设计阶段）

预计改动：

- `src/api/main.py`（新增兼容路由）
- `src/db/memory.py`（补充当天会话查询能力）
- `src/config/settings.py`（新增兼容时区配置读取）
- `src/chat/client.py` 或新增兼容编排模块（注入运行时提示并聚合响应）
- `tests/integration/*`（新增兼容契约与会话时区测试）
- `tests/unit/*`（新增参数/时区/聚合单测）

## 风险与缓解

1. 风险：内部事件聚合遗漏，导致 `related_articles` 不稳定。
- 缓解：定义聚合器白名单解析规则，并提供降级为空数组。

2. 风险：时区边界（跨日）导致会话选择错误。
- 缓解：统一在数据库查询层使用显式时区转换，并补充跨日测试样例。

3. 风险：兼容层侵入现有聊天流程。
- 缓解：兼容逻辑独立服务化封装，避免污染 `/chat` 主流程。

## 结论

采用“本地兼容层 + 现有能力复用”的方案，在最小改动范围内满足旧协议兼容、会话语义升级与可观测测试保障，且未来技术债最低。
