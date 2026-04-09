# 记忆触发整合方案（回合末强制执行 + 提示词合并 + DB 工具门控）

- 日期: 2026-04-09
- 状态: 设计确认（会话确认）
- 范围: ai_end 中 form_memory 触发语义、提示词合并约束、DB skill tools 暴露策略
- 非目标: 不改数据库结构、不新增迁移、不改 MemoryManager 解析/重试协议

## 1. 背景与整合目标

当前存在两类已确认方向：

1. AI 主动调用 form_memory 时，应在回合末统一执行，不在 tool_call 当下立即写入。
2. 提示词层需承担“已有画像 + 当前对话合并输出完整 v2、冲突新优先、提问不直接进 confirmed”的约束。

本次整合追加一项约束：

1. 在 DB skill tools 列表中硬编码提供 form_memory 定义。
2. 但 form_memory 仅在会话存在 user_id 时对模型暴露。

整合目标：

1. 统一触发链路，不引入新分叉执行路径。
2. 回合内多次触发 form_memory 仅执行一次。
3. 强制路径绕过 5 条门槛，普通自动触发保持门槛不变。
4. 提示词层合并规则继续生效。

## 2. 方案对比与推荐

### 2.1 方案 A（推荐，技术债最低）

- form_memory tool_call 仅登记本回合强制标记。
- 回合末统一裁决并最多执行一次 form_memory。
- DB tools 中硬编码 form_memory，但按 user_id 门控暴露。

优点：

1. 触发语义清晰，避免双写与状态分叉。
2. 复用 MemoryManager 单一执行入口，改动面小。
3. 同时满足激进触发、提示词合并、匿名会话不暴露 form_memory。

### 2.2 方案 B

- form_memory 始终暴露；无 user_id 时由 handler 拒绝。

缺点：

1. 不满足“无 user_id 不暴露工具”的约束。
2. 模型可能在匿名会话反复误调，增加噪声与 token 开销。

### 2.3 方案 C

- 全量 tools 先构建，再由 client 层二次过滤。

缺点：

1. 需要新增策略层，当前需求下复杂度偏高。
2. 技术债高于方案 A。

结论：采用方案 A。

## 3. 架构与职责边界

### 3.1 触发层与执行层分离

- 触发层（client + handlers）负责意图登记、回合裁决与门槛判断。
- 执行层（MemoryManager）负责生成、校验、重试、保存。

### 3.2 form_memory 工具语义调整

- handlers 接收 form_memory 后不直接调用 MemoryManager。
- 仅返回“已登记，本回合结束执行”的工具结果。
- 将执行意图通过回合态标记传给 client。

### 3.3 回合末统一执行点

在 client 的“无 tool_calls，准备结束回合”分支按顺序裁决：

1. 若强制标记为 true，执行一次 form_memory，忽略 5 条门槛。
2. 若强制标记为 false，按 `(synced_history_count + 2) >= 5` 判断自动触发。
3. 两条路径互斥。

### 3.4 DB skill tools 中 form_memory 的门控

- DbSkillSystem 中硬编码 form_memory tool 定义。
- build_tools_definition 根据会话上下文判断是否注入：
  - 有 user_id: 注入。
  - 无 user_id: 不注入。

## 4. 状态机与数据流

### 4.1 新增瞬时状态位

- 建议字段: `_force_memory_after_turn: bool`
- 默认 false，仅当前回合有效，不持久化。

### 4.2 状态流转

1. 收到 AI form_memory tool_call -> `_force_memory_after_turn = true`。
2. 回合末裁决：
   - true: 执行一次记忆生成（绕过 5 条门槛）。
   - false: 走原 5 条门槛逻辑。
3. 回合末无论成功、失败或异常都清零为 false。

### 4.3 幂等与去重

- 同回合多次 form_memory tool_call 仅置位一次。
- 回合末最多执行一次记忆生成。

## 5. 提示词整合约束（沿用并加强）

### 5.1 SYSTEM_PROMPT 触发策略

保留并强化以下语义：

1. 用户出现身份/偏好/约束/长期目标线索时，优先触发 form_memory。
2. 不要求用户明确说“请记住”。

### 5.2 MEMORY_PROMPT 合并策略

保留以下硬约束：

1. 必须基于“已有画像 + 当前对话”输出合并后的完整 v2 JSON。
2. 冲突时新信息优先。
3. 用户明确否定旧偏好时，旧偏好不得保留在 confirmed.interests。

### 5.3 confirmed 门槛约束

保留以下负面约束：

1. 提问某主题不等于 confirmed 兴趣。
2. 提问线索最多进入 hypothesized.interests 或 pending_queries。
3. 仅明确偏好表达可进入 confirmed.interests。

## 6. 异常处理与边界约束

1. 强制路径只绕过轮数门槛，不绕过 user_id、消息非空等基础前置条件。
2. 记忆生成失败沿用现有重试与失败返回，不中断主聊天流程。
3. 回合中断必须清理强制标记，防止污染下一回合。
4. 强制路径与普通自动路径互斥，避免双写。
5. 无 user_id 会话不暴露 form_memory 工具，减少误调。

## 7. 测试策略（TDD）

### 7.1 RED：先补失败用例

1. handlers 单测
   - form_memory tool_call 不直接执行 MemoryManager。
   - 返回“回合末执行”语义文案。

2. client 单测
   - 强制标记 true 时，未达 5 条也会回合末执行 form_memory。
   - 同回合多次触发仅执行一次。
   - 回合结束后标记被清零（成功/失败均覆盖）。

3. db_skill_system 单测
   - 有 user_id 时，tools 包含 form_memory。
   - 无 user_id 时，tools 不包含 form_memory。

4. prompts 回归
   - SYSTEM_PROMPT 含激进触发语义。
   - MEMORY_PROMPT 含合并与 confirmed 门槛语义。

### 7.2 GREEN：最小实现通过测试

- 仅改 handlers/client/db_skill_system/prompts_runtime 调度与门控。
- 不改 MemoryManager 解析与存储协议。
- 不新增数据库迁移。

## 8. 验收标准

1. AI 主动触发后，本回合结束必定执行一次记忆生成。
2. 该执行不受最低轮数门槛限制。
3. 普通自动触发仍受 5 条门槛限制。
4. 同回合多次触发只执行一次。
5. 失败不阻断主流程且不泄漏状态到下一回合。
6. DB tools 中 form_memory 按 user_id 门控暴露。
7. 提示词仍满足“合并输出完整 v2 + confirmed 门槛”约束。
8. 无数据库迁移与 schema 改动。

## 9. 发布与回滚

### 9.1 发布策略

1. 按 TDD 先 RED 后 GREEN 小步推进。
2. 先跑 unit，再跑 memory 相关 integration。
3. 上线前关注匿名会话工具列表与记忆触发日志，确认门控与回合末执行生效。

### 9.2 回滚策略

1. 回滚 handlers/client 的强制标记与回合末优先裁决逻辑。
2. 回滚 DbSkillSystem 对 form_memory 的 user_id 门控逻辑。
3. MemoryManager 与数据层不变，无迁移回滚风险。

## 10. 后续执行入口

下一步进入 implementation plan 阶段，输出可执行的任务拆分、命令与验收清单。