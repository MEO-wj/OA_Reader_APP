# 记忆系统 v2 统一链路与重试校验设计

- 日期: 2026-04-08
- 状态: 评审通过（本次会话确认）
- 基线文档:
  - docs/archive/2026-04-07-memory-schema-v2-design.md
  - docs/plans/2026-04-08-memory-json-validation-retry-design.md
- 范围: ai_end 记忆生成、校验、重试、统一入口、渲染兼容
- 非目标: 不改数据库结构、不新增迁移、不改 API schema

## 1. 目标

1. 统一自动记忆与 form_memory 工具路径，消除解析分叉。
2. 记忆落库前强制进行 JSON 语法和 v2 结构校验。
3. 可重试内容错误最多重试 2 次（总尝试 3 次）。
4. 超限后跳过保存，不阻断主聊天流程。
5. portrait_text / knowledge_text 统一存储为 v2 JSON 字符串。
6. form_memory 对外采用结构化返回契约，由上层再渲染为文本。

## 2. 核心约束

1. 不变更 user_profiles 表结构，继续使用 TEXT 字段 portrait_text / knowledge_text。
2. 新写入全部采用 v2 结构。
3. 读取到 v1 或非法 JSON，按空画像处理，不注入旧结构。
4. confirmed 与 hypothesized 严格分层。
5. 禁止仅凭 OA 阅读行为将身份写入 confirmed.identity。

## 3. 推荐方案（低技术债）

采用 MemoryManager 单一真相源方案（推荐）：

1. MemoryManager 统一负责: 生成 -> 校验 -> 裁决 -> 重试 -> 保存。
2. 自动记忆路径直接调用统一入口。
3. form_memory 工具路径改为薄适配层，只做参数输入和结果文本包装。
4. client 仅负责读取/渲染，不承担记忆生成逻辑。

理由:

1. 解析与重试都在同一处，后续需求扩展不易分叉。
2. 工具路径与自动路径结果一致，测试复杂度显著降低。
3. 变更点集中在 chat 层，避免跨层耦合和数据库风险。

## 4. 模块职责

### 4.1 MemoryManager（src/chat/memory_manager.py）

新增统一入口（示意）：

- 输入: messages、user_id、conversation_id、trigger_reason（可选）
- 输出: MemorySaveResult（结构化）

结构化返回建议:

```json
{
  "saved": true,
  "attempts_used": 1,
  "last_error": "",
  "skip_reason": "",
  "portrait_text": "{...v2 json string...}",
  "knowledge_text": "{...v2 json string...}"
}
```

其中:

1. saved=false 时仍返回 attempts_used/last_error/skip_reason 供上层决策。
2. 所有可重试错误都在此层处理，不外泄重试细节。

### 4.2 handlers（src/chat/handlers.py）

1. handle_form_memory 不再独立正则解析。
2. 仅负责读取历史消息并调用 MemoryManager 统一入口。
3. 接收结构化结果后，按当前产品语气拼装用户可读字符串。

### 4.3 client（src/chat/client.py）

1. 仅负责画像加载与系统提示注入。
2. 渲染层解析 v2: confirmed/hypothesized/knowledge。
3. v1 或非法 JSON 渲染为空画像，并对 hypothesized 增加警示。

### 4.4 prompts_runtime（src/chat/prompts_runtime.py）

1. MEMORY_PROMPT_TEMPLATE 输出严格 v2 JSON。
2. FORM_MEMORY_PROMPT_TEMPLATE 语义与 v2 对齐。
3. SYSTEM_PROMPT_TEMPLATE/COMPACT_PROMPT_TEMPLATE 保留分层约束。

## 5. 数据流与重试协议

### 5.1 单次尝试

1. 基于 messages 构建 prompt 并调用 LLM。
2. 依次执行:
   - JSON 语法校验
   - v2 结构校验
   - identity 二次裁决
   - 裁决后二次结构校验
3. 通过后写入 portrait_text / knowledge_text。

### 5.2 重试规则

1. 总尝试次数为 3（首次 + 重试 2 次）。
2. 每次失败把 last_error 拼接到下一次请求。
3. 重试上下文仅保留 messages + 上一次错误原因。
4. 重试阶段不额外追加“用户已保存画像”内容。

### 5.3 超限行为

1. 第 3 次失败返回 saved=false。
2. 返回 attempts_used=3 与 last_error。
3. 跳过保存，不抛致命异常，不影响主流程响应。

## 6. Schema v2（存储形态）

### 6.1 portrait_text

```json
{
  "confirmed": {
    "identity": ["..."],
    "interests": ["..."],
    "constraints": ["..."]
  },
  "hypothesized": {
    "identity": ["（来源：...）可能..."],
    "interests": ["（来源：...）可能..."]
  }
}
```

### 6.2 knowledge_text

```json
{
  "knowledge": {
    "confirmed_facts": ["..."],
    "pending_queries": ["..."]
  }
}
```

## 7. 身份裁决规则

1. confirmed.identity 命中推断词（可能/推测/频繁阅读/多次查询/来源）则降级到 hypothesized.identity。
2. 降级项无来源标记时补前缀“（来源未确认）”。
3. confirmed.identity 只保留用户明确表达事实。

## 8. 错误分类

### 8.1 可重试错误

1. 非 JSON。
2. v2 结构不匹配。
3. 字段类型非法。
4. 裁决后二次校验失败。

### 8.2 不可重试错误

1. 数据库写入失败。
2. 数据库连接异常。
3. 基础设施故障（非模型内容问题）。

### 8.3 空消息

1. 直接跳过保存。
2. 返回 skip_reason=no_messages。

## 9. 测试策略（TDD）

### 9.1 MemoryManager 单测

1. v2 正常解析并保存成功。
2. 非 JSON -> 重试后成功。
3. 连续 3 次失败 -> saved=false 且跳过保存。
4. 重试请求包含 messages + last_error。
5. 重试阶段不追加已保存画像。
6. identity 降级与来源补齐。

### 9.2 双路径一致性测试

1. 自动路径与工具路径同输入得到同结构。
2. 两路径都调用 MemoryManager 单入口。

### 9.3 client 渲染测试

1. v2 分层渲染正确。
2. v1/非法 JSON 渲染为空画像。
3. hypothesized 显示警示文案。

## 10. 验收标准

1. 无数据库迁移改动。
2. 新写入全部为 v2 JSON 字符串。
3. 保存前完成 JSON + 结构校验。
4. 重试规则为最多 3 次。
5. 超限后跳过保存且不影响主流程。
6. 自动路径与工具路径无解析分叉。

## 11. 实施建议

1. 先补测试（MemoryManager 单测 + 双路径一致性）。
2. 再做统一入口改造和 handlers 适配。
3. 最后调整 client 渲染与提示词回归断言。
4. 每一步都以最小改动提交，避免跨模块大爆炸。
