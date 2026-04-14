# 代码审查问题修复设计文档

**日期**: 2026-04-14
**审查范围**: f50b92fd..b3f54de (feat/ai_todolist 分支)
**策略**: 方案 A — 最小化修复，零技术债增长

## 概述

对 feat/ai_todolist 分支 6 个 commit（16 文件，+2361/-109 行）的代码审查发现 13 个问题（3 Critical / 5 Important / 5 Minor），本文档设计全部修复方案。

## Critical 修复

### C1: `_merge_portraits` 返回类型注解与实际不一致

**文件**: `ai_end/src/chat/memory_manager.py` 第 317-319 行

- 返回类型 `dict[str, Any] | None` → `dict[str, Any]`
- docstring 移除"全部重试失败返回 None"描述
- 调用方 `form_memory` 第 119 行逻辑不变

### C2: 集成测试 `SAMPLE_CONVERSATION` 重复定义

**文件**: `ai_end/tests/integration/test_profile_integration.py` 第 94-102 行

- 删除第二个 `SAMPLE_CONVERSATION` 定义及注释

### C3: `test_memory_manager.py` 文件末尾缺少换行符

**文件**: `ai_end/tests/unit/test_memory_manager.py`

- 末尾添加换行符

## Important 修复

### I1+I2: 删除死代码及清理 MEMORY_PROMPT_TEMPLATE

**删除的方法** (`memory_manager.py`):
- `_build_memory_prompt` (第 150-159 行)
- `_load_existing_profile` (第 161-227 行)
- `_build_retry_prompt` (第 262-273 行)

**导入清理** (`memory_manager.py` 第 8 行):
- 移除 `MEMORY_PROMPT_TEMPLATE` 导入

**删除常量** (`prompts_runtime.py` 第 62-100 行):
- `MEMORY_PROMPT_TEMPLATE` 整个定义

**删除测试常量** (`prompts_test_constants.py`):
- `MEMORY_V2_REQUIRED_FIELDS`
- `MEMORY_V2_REQUIRED_CONSTRAINTS`

**删除测试方法** (`test_prompts_runtime.py`):
- `test_memory_prompt_contains_v2_fields`
- `test_memory_prompt_contains_identity_constraint`
- `test_memory_prompt_contains_existing_profile_placeholder`
- `test_memory_prompt_contains_merge_and_conflict_rules`
- `test_memory_prompt_contains_confirmed_interests_threshold`
- `test_memory_prompt_still_exists_for_compatibility`

**更新测试** (`test_prompts_runtime.py`):
- `test_runtime_prompt_constants_exist` 的 required 列表移除 `"MEMORY_PROMPT_TEMPLATE"`

**删除测试方法** (`test_memory_manager.py`):
- `TestMemoryManager.test_memory_prompt_uses_runtime_template`（通过 inspect 检查已删除方法的测试）

### I3: `todolist_check` 硬编码注入

**文件**: `ai_end/src/chat/handlers.py` 第 207-209 行

**决策**: 保持现状，添加 TODO 注释说明未来扩展方向。

### I4: `check_step` 未校验非法 status

**文件**: `ai_end/src/core/todolist_handler.py`

- 在 `called_tools` 校验后添加 `VALID_STATUSES = {"start", "done", "skip"}` 校验
- 非法 status 返回 `success=False` 错误
- 新增测试用例验证非法 status

### I5: `_extract_portrait` 重试未携带前次错误信息

**文件**: `ai_end/src/chat/memory_manager.py` 第 289-290 行

- 重试时（attempt > 1）在 prompt 末尾附加前次错误信息
- 新增/更新测试验证重试 prompt 包含错误信息

## Minor 修复

### M1: `_validate_done` tool_desc 自动推导

**文件**: `ai_end/src/core/todolist_handler.py`

- 移除 `tool_desc` 参数，从 `REQUIRED_TOOLS[step]` 自动生成
- 调用处同步简化

### M2: `processed_tools` 语义注释

**文件**: `ai_end/src/chat/handlers.py` 第 160 行

- 添加注释说明语义为"已尝试"而非"已成功"

### M3: SKILL.md 步骤 1 补充触发条件示例

**文件**: `ai_end/skills/todolist/SKILL.md`

- 步骤 1 补充触发示例和不触发示例

### M4: PORTRAIT_EXTRACT_PROMPT 补充防误判约束

**文件**: `ai_end/src/chat/prompts_runtime.py`

- confirmed 规则补充"禁止将未经验证的行为推断写入 confirmed"

### M5: CLAUDE.md 文档路径描述

- 确认 `docs/plans/` 为项目级文档路径，无需变更

## 影响文件汇总

| 文件 | 变更类型 |
|------|---------|
| `ai_end/src/chat/memory_manager.py` | C1 + I1/I2 + I5 |
| `ai_end/tests/integration/test_profile_integration.py` | C2 |
| `ai_end/tests/unit/test_memory_manager.py` | C3 + I1 |
| `ai_end/src/chat/prompts_runtime.py` | I1/I2 + M4 |
| `ai_end/tests/prompts_test_constants.py` | I1/I2 |
| `ai_end/tests/unit/test_prompts_runtime.py` | I1/I2 |
| `ai_end/src/core/todolist_handler.py` | I4 + M1 |
| `ai_end/tests/unit/test_todolist_handler.py` | I4 新增测试 |
| `ai_end/skills/todolist/SKILL.md` | M3 |
| `ai_end/src/chat/handlers.py` | I3 + M2 |
