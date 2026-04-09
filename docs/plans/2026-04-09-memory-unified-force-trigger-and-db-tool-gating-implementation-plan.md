# Memory Unified Force Trigger And DB Tool Gating Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不修改数据库结构的前提下，实现 form_memory 的回合末强制执行语义，并在 DB tools 中按 user_id 门控暴露 form_memory。

**Architecture:** 采用触发层与执行层分离。tool_call 阶段仅登记强制记忆意图，回合末统一裁决并调用 MemoryManager 单一入口。DbSkillSystem 负责 form_memory 工具定义与 user_id 条件注入，client 负责上下文透传与回合状态清理。

**Tech Stack:** Python 3.11+, pytest, async/await, OpenAI tools schema, 现有 ChatClient/DbSkillSystem/handlers 组件。

---

### Task 1: form_memory 工具门控测试先行（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_db_skill_system.py`
- Test: `ai_end/tests/unit/test_db_skill_system.py`

**Step 1: Write the failing test**

在 `TestDbSkillSystem` 新增测试：

```python
async def test_build_tools_definition_has_form_memory_with_user_id(self, mock_db_rows):
    with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
        mock_get_pool.return_value = create_mock_pool(mock_db_rows)
        system = await DbSkillSystem.create()

        tools = system.build_tools_definition(activated_skills=set(), user_id="u1")
        names = [t["function"]["name"] for t in tools]
        assert "form_memory" in names

async def test_build_tools_definition_hides_form_memory_without_user_id(self, mock_db_rows):
    with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
        mock_get_pool.return_value = create_mock_pool(mock_db_rows)
        system = await DbSkillSystem.create()

        tools = system.build_tools_definition(activated_skills=set(), user_id=None)
        names = [t["function"]["name"] for t in tools]
        assert "form_memory" not in names
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_db_skill_system.py -k form_memory -v`
Expected: FAIL，提示 `build_tools_definition()` 不接受 `user_id` 或未注入 `form_memory`。

**Step 3: Write minimal implementation**

在 `ai_end/src/core/db_skill_system.py` 最小改动：

1. 修改方法签名：

```python
def build_tools_definition(self, activated_skills: set[str] | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
```

2. 在方法末尾添加 form_memory 工具定义（硬编码）。
3. 仅在 `user_id` 存在时 append form_memory。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_db_skill_system.py -k form_memory -v`
Expected: PASS。

### Task 2: client 透传 user_id 到 tools 构建（RED->GREEN）

**Files:**
- Modify: `ai_end/src/chat/client.py`
- Modify: `ai_end/tests/unit/test_memory_chat.py`
- Test: `ai_end/tests/unit/test_memory_chat.py`

**Step 1: Write the failing test**

在 `test_memory_chat.py` 新增测试，验证 `chat` 与 `chat_stream_async` 调用 tools 构建时透传 user_id。

```python
@pytest.mark.asyncio
async def test_chat_stream_passes_user_id_to_build_tools_definition(monkeypatch):
    config = Config.load()
    client = ChatClient(config)
    client.user_id = "u1"

    captured = {}
    original = client.skill_system.build_tools_definition

    def wrapped(*args, **kwargs):
        captured.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(client.skill_system, "build_tools_definition", wrapped)
    async for event in client.chat_stream_async("hello"):
        if event.get("type") == "done":
            break

    assert captured.get("user_id") == "u1"
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py -k build_tools_definition -v`
Expected: FAIL，`user_id` 未被传入。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/client.py` 两处调用同步修改：

1. `chat()` 内：
`self.skill_system.build_tools_definition(self.activated_skills, user_id=self.user_id)`
2. `chat_stream_async()` 内同样透传 `user_id=self.user_id`。

兼容性要求：若当前 skill_system 为文件系统旧实现，也应允许新增可选参数（或由适配层吸收）。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py -k build_tools_definition -v`
Expected: PASS。


### Task 3: form_memory tool_call 改为登记回合末执行（RED）

**Files:**
- Modify: `ai_end/src/chat/handlers.py`
- Modify: `ai_end/tests/unit/test_handlers.py`
- Test: `ai_end/tests/unit/test_handlers.py`

**Step 1: Write the failing test**

新增测试覆盖：

1. form_memory 被调用时不触发 MemoryManager。
2. 返回“已登记，将在回合末执行”文案。
3. 支持通过回调登记状态。

示例：

```python
@pytest.mark.asyncio
async def test_form_memory_tool_only_registers_after_turn_flag():
    marked = {"value": False}

    def mark():
        marked["value"] = True

    # 构造 form_memory tool_call 后调用 handle_tool_calls(..., mark_form_memory_after_turn=mark)
    # 断言：marked 为 True，且未调用 handle_form_memory
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_handlers.py -k form_memory -v`
Expected: FAIL，当前逻辑仍立即调用 `handle_form_memory`。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/handlers.py`：

1. `handle_tool_calls` 增加可选参数 `mark_form_memory_after_turn: Callable[[], None] | None = None`。
2. `function_name == "form_memory"` 分支改为：
   - 若存在回调则调用回调。
   - 返回登记成功文案，不调用 `handle_form_memory`。
3. `handle_tool_calls_sync` 增加同名透传参数。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_handlers.py -k form_memory -v`
Expected: PASS。


### Task 4: client 回合末强制裁决与状态清理（RED->GREEN）

**Files:**
- Modify: `ai_end/src/chat/client.py`
- Modify: `ai_end/tests/unit/test_memory_chat.py`
- Test: `ai_end/tests/unit/test_memory_chat.py`

**Step 1: Write the failing test**

新增测试：

1. `force_memory_after_turn=True` 时，即使未达 5 条门槛也会执行一次 `form_memory()`。
2. 同回合多次 form_memory tool_call 仍仅执行一次。
3. 成功/失败后标记都会清零。
4. 未置位时仍保留 5 条门槛行为。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py -k force_memory_after_turn -v`
Expected: FAIL，当前无该状态机。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/client.py`：

1. 初始化状态字段 `_force_memory_after_turn = False`。
2. 调用 `handle_tool_calls` 时传入标记回调（置 true）。
3. 在“无 tool_calls”回合结束分支：
   - 优先判断 `_force_memory_after_turn` 并执行 `await self.form_memory()`。
   - 否则走 `(synced_history_count + 2) >= 5`。
4. 使用 `try/finally` 或等价结构保证回合末清零。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py -k "force_memory_after_turn or form_memory" -v`
Expected: PASS。


### Task 5: 提示词约束回归（RED->GREEN）

**Files:**
- Modify: `ai_end/src/chat/prompts_runtime.py`
- Modify: `ai_end/tests/unit/test_prompts_runtime.py`
- Test: `ai_end/tests/unit/test_prompts_runtime.py`

**Step 1: Write the failing test**

新增断言：

1. SYSTEM_PROMPT 含“出现画像线索优先触发 form_memory”。
2. MEMORY_PROMPT 含“已有+当前合并输出完整 v2、冲突新优先”。
3. MEMORY_PROMPT 含“提问不直接进入 confirmed.interests”。

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_prompts_runtime.py -k "form_memory or confirmed or merge" -v`
Expected: FAIL（若当前文案不完整）。

**Step 3: Write minimal implementation**

只在 `prompts_runtime.py` 补充必要语义，不改变结构。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_prompts_runtime.py -v`
Expected: PASS。


### Task 6: 集成回归与发布前验证

**Files:**
- Test: `ai_end/tests/integration/test_profile_integration.py`
- Test: `ai_end/tests/integration/test_skill_flow.py`
- Optional Modify: `ai_end/tests/integration/test_profile_integration.py`（按需补例）

**Step 1: Write/adjust failing integration tests**

补充或调整集成断言：

1. 强制标记路径未达 5 条也会在回合末执行。
2. 未强制路径仍受 5 条门槛限制。
3. 无 user_id 时 tools 不包含 form_memory。

**Step 2: Run tests to verify they fail before implementation (if newly added)**

Run: `cd ai_end; pytest tests/integration/test_profile_integration.py tests/integration/test_skill_flow.py -v`
Expected: 新增断言先 FAIL（若此前未实现）。

**Step 3: Run full memory-related verification**

Run:

```bash
cd ai_end
pytest tests/unit/test_db_skill_system.py -v
pytest tests/unit/test_handlers.py -k form_memory -v
pytest tests/unit/test_memory_chat.py -v
pytest tests/unit/test_prompts_runtime.py -v
pytest tests/integration/test_profile_integration.py tests/integration/test_skill_flow.py -v
```

Expected: 全部 PASS。

**Step 4: Sanity check for no schema changes**

Run: `git diff --name-only | findstr /I "migrations sql"`
Expected: 无新增迁移文件。


### Task 7: 文档同步（可选，若与实现偏差）

**Files:**
- Optional Modify: `docs/plans/2026-04-09-memory-unified-force-trigger-and-db-tool-gating-design.md`
- Optional Modify: `ai_end/README.md`

**Step 1: Update docs only if behavior differs from design text**

保持文档与实现一致；不扩展额外特性。

**Step 2: Run lightweight doc sanity check**

Run: `git diff -- docs ai_end/README.md`
Expected: 仅描述性更新。

