# 记忆触发激进化与提示词合并设计

- 日期: 2026-04-08
- 状态: 评审通过（会话确认）
- 基线文档:
  - docs/plans/2026-04-08-memory-unified-v2-retry-design.md
  - docs/plans/2026-04-08-memory-incremental-profile-design.md
- 范围: ai_end 记忆触发策略、MEMORY_PROMPT 合并约束、confirmed 判定门槛
- 非目标: 不改数据库结构、不新增迁移、不新增程序侧 merge 模块

## 1. 背景与问题

用户当前关注三点:

1. form_memory 触发不够主动，需在用户出现画像线索时更激进触发。
2. 不希望“看起来覆盖旧画像”，期望由模型基于已有画像做合并整理，冲突时新信息优先。
3. 不能因用户短期提问 1-2 次某主题，就把兴趣写入 confirmed。

## 2. 目标

1. 保持统一链路不分叉（工具路径和自动路径都走 MemoryManager.form_memory）。
2. 将“合并责任”明确放在 LLM 提示词层，输出合并后的完整 v2 JSON。
3. 强化 confirmed/hypothesized 边界，显式禁止“提问即 confirmed 兴趣”。

## 3. 核心约束

1. 保持现有统一入口：handlers -> MemoryManager.form_memory。
2. 保持现有存储方式：save_profile upsert（覆盖写入）。
3. 覆盖写入的对象必须是“模型合并后的全量画像”，不是本轮孤立增量。
4. 保持 v2 校验、重试协议与主流程容错不退化。
5. 不新增数据库字段和迁移。

## 4. 推荐方案（低技术债）

采用“提示词合并，链路不扩展”方案:

1. 在 MEMORY_PROMPT_TEMPLATE 中明确要求模型读取已有画像并产出合并后的完整 v2 结果。
2. 在 SYSTEM_PROMPT_TEMPLATE 中强化触发策略：用户出现身份/偏好/约束线索时优先触发 form_memory。
3. 在 MEMORY_PROMPT_TEMPLATE 增加 confirmed 门槛规则，禁止将短期提问行为直接写入 confirmed.interests。
4. 保留当前 _parse_memory + save_profile 路径，不引入程序侧 merge 新分支。

## 5. 数据流

```text
chat/tool 触发 form_memory
  -> handlers.handle_form_memory
  -> MemoryManager.form_memory
      -> _build_memory_prompt(messages)
           - 注入 existing_profile（仅首轮）
           - 注入“合并输出完整 v2 JSON”规则
      -> LLM 输出
      -> _parse_memory(v2 校验 + 裁决)
      -> save_profile(upsert 覆盖合并后全量)
```

说明:

1. 统一链路仍成立，未新增并行流程。
2. 覆盖行为保留，但语义变为“覆盖为合并结果”。

## 6. 规则设计

### 6.1 激进触发规则

在 SYSTEM_PROMPT_TEMPLATE 增加规则:

1. 一旦用户表达以下任一线索，优先触发 form_memory:
   - 身份信息（年级、专业、学校、岗位等）
   - 偏好/厌恶（喜欢、不喜欢、倾向、避开）
   - 约束（地域、预算、时间、资格）
   - 长期目标（升学、就业、科研方向）
2. 不要求用户显式说“请记住”。

### 6.2 合并规则（由 LLM 执行）

在 MEMORY_PROMPT_TEMPLATE 增加硬约束:

1. 必须基于“已有画像 + 当前对话”生成合并后的完整 v2 JSON。
2. 发生冲突时以当前对话为准（新覆盖旧）。
3. 若用户明确否定旧偏好（如“我其实不喜欢 X”），旧偏好不得继续保留在 confirmed.interests。

### 6.3 confirmed 门槛

在 MEMORY_PROMPT_TEMPLATE 增加负面约束:

1. 用户提问某主题（即便 1-2 次或多次）不等于 confirmed 兴趣。
2. 提问线索最多进入 hypothesized.interests 或 pending_queries。
3. 仅当用户明确偏好表达（如“我喜欢/我更偏好/我只考虑”）才可写入 confirmed.interests。

## 7. 异常与回退

1. LLM 非 JSON 或 v2 结构不合法：沿用最多 3 次重试。
2. 旧画像非法/v1：按无已有画像处理，不阻断主流程。
3. DB 写入异常：按基础设施错误处理，不进入内容重试。
4. 超限失败：跳过保存，主聊天流程继续。

## 8. 测试策略（TDD）

### 8.1 提示词回归

文件: ai_end/tests/unit/test_prompts_runtime.py

新增断言:

1. SYSTEM_PROMPT_TEMPLATE 包含激进触发 form_memory 的语义。
2. MEMORY_PROMPT_TEMPLATE 包含“已有+当前合并、冲突新优先”语义。
3. MEMORY_PROMPT_TEMPLATE 包含“提问不等于 confirmed.interests”语义。

### 8.2 MemoryManager 回归

文件: ai_end/tests/unit/test_memory_manager.py

新增/调整断言:

1. 首轮 prompt 注入 existing_profile。
2. 重试 prompt 不注入 existing_profile。
3. 首轮 prompt 明确要求输出“合并后的完整 v2 JSON”。

### 8.3 行为防误判

文件: ai_end/tests/unit/test_memory_manager.py

增加场景:

1. 仅有用户提问线索时，兴趣不得进入 confirmed.interests。
2. 有明确偏好表达时，允许进入 confirmed.interests。

## 9. 验收标准

1. 统一链路不分叉（工具路径与自动路径仍统一）。
2. 触发策略较当前更主动，且文案可测试。
3. 旧画像参与模型合并，冲突新优先。
4. “提问 1-2 次”不得直接形成 confirmed 兴趣。
5. 不新增数据库迁移，不破坏现有重试与容错。

## 10. 实施建议

1. 先补提示词与测试断言（RED）。
2. 再最小改动更新 prompts_runtime（GREEN）。
3. 最后跑记忆相关单测回归并修正文案漂移。
