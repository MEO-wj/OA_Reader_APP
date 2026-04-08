# Memory Unified V2 Retry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改数据库结构的前提下，将 ai_end 记忆链路统一到 MemoryManager，完成 v2 JSON 校验、identity 裁决和最多 3 次重试，并让工具路径与自动路径输出一致。

**Architecture:** 采用 MemoryManager 单一真相源。自动触发和 form_memory 工具都调用同一入口，handlers 仅做适配层，client 仅负责 v2 渲染。通过单测先行锁定结构化返回契约与重试协议，再做最小实现。

**Tech Stack:** Python 3.11, pytest, unittest.mock, ai_end chat module

---

### Task 1: 锁定提示词与 v2 契约（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_prompts_runtime.py`
- Modify: `ai_end/src/chat/prompts_runtime.py`
- Test: `ai_end/tests/unit/test_prompts_runtime.py`

**Step 1: Write the failing test**

在 `ai_end/tests/unit/test_prompts_runtime.py` 新增断言：
1. `MEMORY_PROMPT_TEMPLATE` 包含 `confirmed` / `hypothesized` / `knowledge.confirmed_facts` / `knowledge.pending_queries`。
2. 包含“禁止仅凭 OA 阅读记录写 confirmed.identity”的约束文案。
3. `COMPACT_PROMPT_TEMPLATE` 包含“不可把 hypothesized 合并到 confirmed”的约束文案。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/unit/test_prompts_runtime.py -q`
Expected: FAIL，提示缺失 v2 字段或禁止条款。

**Step 3: Write minimal implementation**

更新 `ai_end/src/chat/prompts_runtime.py`：
1. 将 `MEMORY_PROMPT_TEMPLATE` 改为严格 v2 JSON 输出。
2. 将 `FORM_MEMORY_PROMPT_TEMPLATE` 对齐 v2 语义层。
3. 为 `SYSTEM_PROMPT_TEMPLATE` 和 `COMPACT_PROMPT_TEMPLATE` 增加分层与禁止合并约束。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/unit/test_prompts_runtime.py -q`
Expected: PASS。

### Task 2: 定义 MemoryManager 结构化返回契约（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py`
- Modify: `ai_end/src/chat/memory_manager.py`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing test**

在 `ai_end/tests/unit/test_memory_manager.py` 新增测试：
1. `form_memory` 返回结构化对象字段：`saved`、`attempts_used`、`last_error`、`skip_reason`、`portrait_text`、`knowledge_text`。
2. `user_id` 为空时 `saved=false` 且 `skip_reason=no_user_id`。
3. `messages` 为空时 `saved=false` 且 `skip_reason=no_messages`。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py -q`
Expected: FAIL，当前返回仅有 portrait/knowledge。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/memory_manager.py`：
1. 新增内部结果结构（dict 或 dataclass）。
2. 更新 `form_memory` 返回契约，保留向后兼容字段（若需要）。
3. 在无 user_id / 无 messages 时直接返回 skip 结果，不落库。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py -q`
Expected: PASS。


### Task 3: 增加 v2 校验与 identity 裁决（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py`
- Modify: `ai_end/src/chat/memory_manager.py`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing test**

新增测试用例：
1. v2 合法 JSON 可通过并生成 `portrait_text`/`knowledge_text`。
2. v1 JSON（`hard_constraints` 等）视为空画像。
3. `confirmed.identity` 中推断项降级到 `hypothesized.identity`。
4. 降级条目缺来源时自动补 `（来源未确认）` 前缀。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py -q`
Expected: FAIL，当前解析仍是 v1 字段。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/memory_manager.py` 新增：
1. `_validate_v2_memory_schema(data)`
2. `_adjudicate_identity(portrait_obj)`
3. `_normalize_string_list(value)`
4. `_parse_memory` 改为输出 v2 的 `portrait_text`/`knowledge_text`。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py -q`
Expected: PASS。

### Task 4: 增加重试协议（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py`
- Modify: `ai_end/src/chat/memory_manager.py`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing test**

新增测试：
1. 非 JSON 第 1 次失败，第 2 次成功，`attempts_used=2`。
2. 连续 3 次失败，`saved=false` 且 `attempts_used=3`。
3. 重试请求仅包含 `messages + last_error`，不追加已保存画像。
4. DB 异常属于不可重试错误，直接抛出或标记 infra error。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py -q`
Expected: FAIL，当前无重试循环。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/memory_manager.py`：
1. 封装 `_form_memory_once` 与 `_build_retry_prompt`。
2. `for attempt in range(1, 4)` 重试循环。
3. 内容错误重试，基础设施错误不重试。
4. 失败超限返回结构化 skip 结果。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py -q`
Expected: PASS。

### Task 5: tools 路径接入统一入口（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_handlers.py`
- Modify: `ai_end/src/chat/handlers.py`
- Test: `ai_end/tests/unit/test_handlers.py`

**Step 1: Write the failing test**

在 `ai_end/tests/unit/test_handlers.py` 新增测试：
1. `handle_form_memory` 调用 `MemoryManager.form_memory`，不再走本地正则解析。
2. `handle_form_memory` 接收结构化结果后生成用户可读字符串。
3. 失败时返回包含 `saved=false` 对应提示文案。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/unit/test_handlers.py -q`
Expected: FAIL，当前 handlers 仍有独立解析分支。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/handlers.py`：
1. 删除 `handle_form_memory` 内独立标签解析与旧格式拼接逻辑。
2. 构建 `MemoryManager(user_id, conversation_id, ...)` 并调用统一入口。
3. 将结构化结果映射为最终文本返回。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/unit/test_handlers.py -q`
Expected: PASS。

### Task 6: client 渲染升级到 v2 分层（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_chat_client.py`
- Modify: `ai_end/src/chat/client.py`
- Test: `ai_end/tests/unit/test_chat_client.py`

**Step 1: Write the failing test**

新增测试：
1. `_parse_profile_to_sections` 支持 v2 的 confirmed/hypothesized/knowledge。
2. v1 与非法 JSON 返回“（暂无）”分层。
3. system prompt 对 hypothesized 区块有“仅供参考”警示。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/unit/test_chat_client.py -q`
Expected: FAIL，当前仍按 v1 字段解析。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/client.py`：
1. 重写 `_parse_profile_to_sections` 解析 v2。
2. 在 `_build_system_prompt` 添加 hypothesized 警示区块。
3. 兼容缺字段，统一回退“（暂无）”。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/unit/test_chat_client.py -q`
Expected: PASS。

### Task 7: 双路径一致性集成验证

**Files:**
- Modify: `ai_end/tests/integration/test_profile_integration.py`
- Test: `ai_end/tests/integration/test_profile_integration.py`

**Step 1: Write the failing test**

新增/重构集成测试：
1. 自动路径触发与 form_memory 工具路径在同输入下保存同结构。
2. 写入库中的 `portrait_text` 与 `knowledge_text` 均为 v2 JSON 字符串。
3. 三次失败后主流程仍返回聊天结果，不中断。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; uv run pytest tests/integration/test_profile_integration.py -q`
Expected: FAIL，当前两路径实现不一致。

**Step 3: Write minimal implementation**

若前述任务已完成，此步骤应仅需微调 mocks/断言。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; uv run pytest tests/integration/test_profile_integration.py -q`
Expected: PASS。

### Task 8: 回归与验收

**Files:**
- Modify: `ai_end/tests/unit/test_prompts_runtime.py`（如有回归修正）
- Test: `ai_end/tests/unit/test_memory_manager.py`
- Test: `ai_end/tests/unit/test_handlers.py`
- Test: `ai_end/tests/unit/test_chat_client.py`
- Test: `ai_end/tests/integration/test_profile_integration.py`

**Step 1: Run targeted suites**

Run: `cd ai_end; uv run pytest tests/unit/test_memory_manager.py tests/unit/test_handlers.py tests/unit/test_chat_client.py tests/unit/test_prompts_runtime.py tests/integration/test_profile_integration.py -q`
Expected: PASS。

**Step 2: Run broader smoke tests**

Run: `cd ai_end; uv run pytest tests/unit -q`
Expected: PASS 或仅存在历史已知失败（需在 PR 说明列出）。
