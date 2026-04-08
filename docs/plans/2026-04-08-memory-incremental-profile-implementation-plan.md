# Memory Incremental Profile Injection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在记忆生成首轮提示词中注入已存在的 v2 画像上下文，实现增量更新，并修复 I3/S3 测试问题且保持重试协议不变。

**Architecture:** 通过在 `MemoryManager` 中新增一个独立的异步加载函数 `_load_existing_profile`，复用已有 v2 校验逻辑判断是否可注入。首轮 prompt 调用异步构建函数拼接可选的已有画像段落；重试 prompt 维持当前实现，仅附加错误原因，避免历史画像干扰重试收敛。所有变化以测试驱动推进，先补失败测试，再做最小实现，最后回归验证。

**Tech Stack:** Python 3.11, pytest, AsyncMock/unittest.mock, uv

---

### Task 1: 为提示词模板增加 existing_profile 占位符（TDD）

**Files:**
- Modify: `ai_end/tests/unit/test_prompts_runtime.py:60-90`
- Modify: `ai_end/src/chat/prompts_runtime.py:85-130`
- Test: `ai_end/tests/unit/test_prompts_runtime.py`

**Step 1: Write the failing test**

在 `test_memory_prompt_contains_v2_fields` 后新增：

```python
def test_memory_prompt_contains_existing_profile_placeholder():
    """验证 MEMORY_PROMPT_TEMPLATE 支持 existing_profile 占位符。"""
    assert "{existing_profile}" in p.MEMORY_PROMPT_TEMPLATE
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py::test_memory_prompt_contains_existing_profile_placeholder -v`
Expected: FAIL with `AssertionError` (`{existing_profile}` not found)

**Step 3: Write minimal implementation**

在 `MEMORY_PROMPT_TEMPLATE` 的末尾追加：

```python

{existing_profile}
```

并保留原有 `对话内容` 与 `{conversation}`。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py::test_memory_prompt_contains_existing_profile_placeholder -v`
Expected: PASS

### Task 2: 先补首轮 prompt 注入行为测试（RED）

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py:520-760`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing test**

在 `TestRetryProtocol` 中新增 4 个异步测试：

```python
@pytest.mark.asyncio
async def test_first_prompt_includes_existing_profile_when_valid_v2(self):
    ...

@pytest.mark.asyncio
async def test_first_prompt_skips_existing_profile_when_v1(self):
    ...

@pytest.mark.asyncio
async def test_first_prompt_skips_existing_profile_when_invalid_json(self):
    ...

@pytest.mark.asyncio
async def test_first_prompt_skips_existing_profile_when_no_profile(self):
    ...
```

断言重点：
- 有效 v2 时，首轮 prompt 含 `已有用户画像` 段落与格式化字段文本（如 `已确认身份:`）
- v1 / 非法 JSON / 空画像时，首轮 prompt 不含该段落

**Step 2: Run test to verify it fails**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_first_prompt_includes_existing_profile_when_valid_v2 -v`
Expected: FAIL with missing section assertion

**Step 3: Keep production code unchanged (RED checkpoint)**

不修改实现，确保测试确实因缺失功能而失败。

**Step 4: Run a narrow test batch to verify all new RED tests fail for same reason**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -k "first_prompt_.*existing_profile" -v`
Expected: FAIL (all related tests fail with prompt content mismatch)

### Task 3: 实现 _load_existing_profile 与异步 _build_memory_prompt（GREEN）

**Files:**
- Modify: `ai_end/src/chat/memory_manager.py:64-170`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write minimal implementation for async prompt build path**

实现点：
- `form_memory` 首轮从 `prompt = self._build_memory_prompt(messages)` 改为 `prompt = await self._build_memory_prompt(messages)`
- `_build_memory_prompt` 改为 `async def`
- 新增 `_load_existing_profile(self) -> str`

核心实现示例：

```python
async def _build_memory_prompt(self, messages: list[dict[str, Any]]) -> str:
    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    existing_profile = await self._load_existing_profile()
    profile_section = ""
    if existing_profile:
        profile_section = (
            "\n## 已有用户画像（仅供参考，请基于当前对话更新，冲突以当前对话为准）\n"
            + existing_profile
        )
    return MEMORY_PROMPT_TEMPLATE.format(
        conversation=conversation,
        existing_profile=profile_section,
    )
```

`_load_existing_profile` 规则：
- 调 `self.memory_db.get_profile(self.user_id)`
- 解析 `portrait_text`，仅当 `_validate_v2_memory_schema` 通过才注入
- `knowledge_text` 只做宽松 JSON 校验，合法 dict 才提取
- 任一异常路径返回空字符串

**Step 2: Run tests to verify GREEN**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -k "first_prompt_.*existing_profile" -v`
Expected: PASS

**Step 3: Run targeted regression for retry protocol**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_first_fail_second_success_attempts_used_2 -v`
Expected: PASS

**Step 4: Run broader memory manager suite**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -v`
Expected: PASS

### Task 4: 修复 I3 重试断言，防止伪阳性

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py:533-575`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing assertion replacement**

把不稳定断言替换为结构性断言：

```python
assert "你好" in retry_prompt
assert "第1次尝试" in retry_prompt
assert "请严格按要求输出合法 JSON" in retry_prompt
```

**Step 2: Run test to verify it fails before code update (if currently old assertion kept)**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_retry_prompt_contains_messages_and_last_error_only -v`
Expected: FAIL with assertion mismatch

**Step 3: Apply minimal test update**

仅改断言，不改生产代码。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_retry_prompt_contains_messages_and_last_error_only -v`
Expected: PASS


### Task 5: 修复 S3 集成测试 mock JSON 结构

**Files:**
- Modify: `ai_end/tests/integration/test_profile_integration.py:81-120`
- Test: `ai_end/tests/integration/test_profile_integration.py`

**Step 1: Write the failing test expectation**

在 `test_auto_trigger_on_5_rounds` 中保持断言 `save_profile` 被调用，同时确保 mock 的返回内容为 v2 合法结构（`knowledge` 内含两个字段）。

**Step 2: Run test to verify it fails with old mock**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py::TestUserProfileIntegration::test_auto_trigger_on_5_rounds -v`
Expected: FAIL due to parse/save path mismatch

**Step 3: Write minimal implementation (test fixture fix)**

将 mock 响应从：

```python
{"confirmed":...,"hypothesized":...,"confirmed_facts":[],"pending_queries":["分数线"]}
```

改为：

```python
{"confirmed":...,"hypothesized":...,"knowledge":{"confirmed_facts":[],"pending_queries":["分数线"]}}
```

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py::TestUserProfileIntegration::test_auto_trigger_on_5_rounds -v`
Expected: PASS


### Task 6: 验证重试 prompt 不注入已有画像（回归）

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py:533-650`
- Test: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing regression test**

新增测试：

```python
@pytest.mark.asyncio
async def test_retry_prompt_does_not_include_existing_profile_section(self):
    ...
```

断言第 2 次 prompt：
- 包含 `第1次尝试`
- 不包含 `已有用户画像（仅供参考` 段落

**Step 2: Run test to verify it fails (if implementation accidentally injects retry profile)**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_retry_prompt_does_not_include_existing_profile_section -v`
Expected: FAIL (only when regression exists)

**Step 3: Keep/adjust minimal implementation**

确保 `_build_retry_prompt` 只依赖 `messages + last_error`，不调用 `_load_existing_profile`。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_retry_prompt_does_not_include_existing_profile_section -v`
Expected: PASS

### Task 7: 全量验证与交付检查（Verification Before Completion）

**Files:**
- Verify: `ai_end/src/chat/memory_manager.py`
- Verify: `ai_end/src/chat/prompts_runtime.py`
- Verify: `ai_end/tests/unit/test_memory_manager.py`
- Verify: `ai_end/tests/unit/test_prompts_runtime.py`
- Verify: `ai_end/tests/integration/test_profile_integration.py`

**Step 1: Run focused unit suites**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py tests/unit/test_memory_manager.py -v`
Expected: PASS

**Step 2: Run target integration suite**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py -v`
Expected: PASS

**Step 3: Run optional full ai_end tests (if time allows)**

Run: `cd ai_end && uv run pytest -v`
Expected: PASS (or record known unrelated failures)

**Step 4: Inspect diff quality**

Run: `git diff -- ai_end/src/chat/memory_manager.py ai_end/src/chat/prompts_runtime.py ai_end/tests/unit/test_memory_manager.py ai_end/tests/unit/test_prompts_runtime.py ai_end/tests/integration/test_profile_integration.py`
Expected: only planned changes, no unrelated formatting churn
---

## Skill References

- `@test-driven-development`: 每个功能点必须先 RED 再 GREEN。
- `@verification-before-completion`: 声称完成前必须提供测试命令与结果证据。
- `@writing-plans`: 按 2-5 分钟颗粒度拆分步骤并提供完整命令。

## 低技术债执行建议（推荐）

推荐按 Task 1 → 2 → 3 → 4 → 5 → 6 → 7 串行执行（最低技术债路径）：
1. 先锁定模板契约，再引入异步改造，避免在同一提交混合“接口变化 + 行为变化”。
2. I3/S3 作为独立测试修复提交，降低回滚半径。
3. 最后做全量验证，确保重试协议与解析契约无回归。
