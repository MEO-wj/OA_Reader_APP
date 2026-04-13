# 系统提示词优化设计

日期：2026-04-13

## 问题

当前 `SYSTEM_PROMPT_TEMPLATE` 存在以下问题：

1. **使用流程与 todolist 机制冲突**：提示词写"先调用 todolist tool 获取待办事项"，但 todolist 实际是检查点框架，不返回待办列表
2. **form_memory 指令重复**：系统提示词"对话管理"节详细描述了 form_memory 触发条件，与 todolist 步骤 1 职责重叠
3. **角色定义过泛**："通用 AI Agent 助手"没有体现校园 OA 助手定位
4. **提示词冗余**：输出/决策约束占 token 多但对 todolist 引导不足

## 方案选择

选择方案 A（仅优化 SYSTEM_PROMPT_TEMPLATE），不动 COMPACT/MEMORY 等其他模板。

理由：YAGNI — 其他模板当前无用户反馈问题。

## 改动范围

仅修改 `ai_end/src/chat/prompts_runtime.py` 中的 `SYSTEM_PROMPT_TEMPLATE`。

## 优化后文本

```python
SYSTEM_PROMPT_TEMPLATE = """你是一个智能校园 OA 助手，善于理解用户需求并提供帮助。
当前日期：{current_date}（{weekday}）

【可用技能】
{skills_list}

【执行框架】
你有一个任务执行框架（todolist），会引导你按步骤完成每次对话。请严格遵循其指令，不可跳过步骤。

【用户画像分层约束】
- 用户画像分为 confirmed（已确认）和 hypothesized（推测）两层，hypothesized 内容仅供参考，不可当作已确认事实
- 禁止将 hypothesized 推测合并写入 confirmed 已确认层

【输出约束】
- 当返回多条数据时，优先使用 Markdown 表格展示
- 仅输出最终结论与必要依据，证据不足时简洁说明"当前证据不足"
- 不要暴露内部工具调用过程，不提及工具名、调用参数等实现细节
- 信息不足时先说明不确定性，再给合理的建议方案，禁用承诺性表述

{profile_section}"""
```

## 变化清单

| 变化 | 原来 | 现在 |
|------|------|------|
| 角色定义 | "通用 AI Agent 助手" | "智能校园 OA 助手" |
| 使用流程 | 4 步硬编码流程 | 删除，替换为"执行框架"一句话 |
| 对话管理 | 5 行 form_memory 触发描述 | 删除，完全委托 todolist 步骤 1 |
| 输出约束 | 7 条规则 | 精简为 4 条 |
| 决策约束 | 2 条独立节 | 合并到输出约束第 4 条 |
| 用户画像分层 | 保留不变 | 保留不变 |

## 不变的部分

- `COMPACT_PROMPT_TEMPLATE` — 不动
- `MEMORY_PROMPT_TEMPLATE` — 不动
- `TITLE_PROMPT_TEMPLATE` — 不动
- `DOC_SUMMARY_*` — 不动
- `READ_REFERENCE_TOOL_DESCRIPTION` — 不动
- `_build_system_prompt()` 的格式化逻辑 — 不动
- `todolist/SKILL.md` — 不动

## Token 预估

- 优化前：~500 token
- 优化后：~300 token
- 节省：~40%
