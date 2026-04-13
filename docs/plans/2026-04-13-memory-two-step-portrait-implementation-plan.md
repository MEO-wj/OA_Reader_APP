# 记忆保存模块两步式画像生成与合并 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `MemoryManager.form_memory()` 拆成“对话提取 -> 首版快速路径/旧画像合并”两步，保持调用方不变，降低 prompt 职责耦合，并减少旧画像较多时的遗漏与误合。

**Architecture:** Step 1 只读取当前对话并提取新的 v2 画像/知识 JSON；Step 2 在存在已保存画像时，将旧画像与新画像合并后再落库。没有旧画像时走首版快速路径，直接保存 Step 1 结果。实现上复用现有的 `_parse_memory`、`_adjudicate_identity`、`_validate_v2_memory_schema`、`MemoryDB.save_profile()` 和 `ChatClient.form_memory()` 调用入口，不改数据库 schema，也不改调用方协议。

**Tech Stack:** Python 3.11+, pytest, async/await, FastAPI 侧现有 chat/memory 组件

**Design basis:** [docs/plans/2026-04-13-memory-two-step-portrait-design.md](docs/plans/2026-04-13-memory-two-step-portrait-design.md)

---

## 执行前约束

- 工作流技能：@superpowers:writing-plans（本计划已完成）
- 实施技能：@superpowers:executing-plans
- 过程约束：@superpowers:test-driven-development
- 收尾约束：@superpowers:verification-before-completion
- 推荐方案：直接执行本计划中的“双 Prompt + 首版快速路径”方案；这是技术债最少的路径，因为它不改 schema、不改调用方，只替换 MemoryManager 内部编排。

---

### Task 1: 为两步式 prompt 契约补测试

**Files:**
- Modify: `ai_end/tests/prompts_test_constants.py`
- Modify: `ai_end/tests/unit/test_prompts_runtime.py`

**Step 1: Write the failing test**

先补常量与断言，让测试描述新契约，而不是旧的单步合并契约。

在 `ai_end/tests/prompts_test_constants.py` 新增两组期望短语：

```python
PORTRAIT_EXTRACT_REQUIRED_PHRASES = [
    "仅基于对话内容提取",
    "不参考旧画像",
    "confirmed",
    "hypothesized",
    "knowledge",
]

PORTRAIT_MERGE_REQUIRED_PHRASES = [
    "旧画像 JSON",
    "新画像 JSON",
    "冲突时新信息优先",
    "去重",
    "hypothesized 不升入 confirmed",
    "空字段保留旧值",
]
```

在 `ai_end/tests/unit/test_prompts_runtime.py` 新增断言：

```python
def test_portrait_extract_prompt_exists_and_blocks_merge_behavior():
    assert hasattr(p, "PORTRAIT_EXTRACT_PROMPT")
    for phrase in PORTRAIT_EXTRACT_REQUIRED_PHRASES:
        assert phrase in p.PORTRAIT_EXTRACT_PROMPT


def test_portrait_merge_prompt_exists_and_contains_merge_rules():
    assert hasattr(p, "PORTRAIT_MERGE_PROMPT")
    for phrase in PORTRAIT_MERGE_REQUIRED_PHRASES:
        assert phrase in p.PORTRAIT_MERGE_PROMPT
```

再补一条回归断言，确认旧的 `MEMORY_PROMPT_TEMPLATE` 仍保留兼容，但主流程不再依赖它：

```python
def test_memory_prompt_still_exists_for_compatibility():
    assert hasattr(p, "MEMORY_PROMPT_TEMPLATE")
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py -v`

Expected: FAIL，提示 `PORTRAIT_EXTRACT_PROMPT` / `PORTRAIT_MERGE_PROMPT` 尚未定义，或者断言短语不匹配。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/prompts_runtime.py` 添加两段模板常量，保持文案短、约束明确：

```python
PORTRAIT_EXTRACT_PROMPT = """..."""
PORTRAIT_MERGE_PROMPT = """..."""
```

要求：
- `PORTRAIT_EXTRACT_PROMPT` 只接收当前对话，不出现旧画像输入占位符。
- `PORTRAIT_MERGE_PROMPT` 明确接收旧画像和新画像两个 JSON 输入。
- 旧的 `MEMORY_PROMPT_TEMPLATE` 保留，不删不改其兼容性字段。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py -v`

Expected: PASS。

---

### Task 2: 为 MemoryManager 的两步式流程补单元测试

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing test**

新增 4 类测试，先把行为边界写清楚：

1. Step 1 只根据当前对话提取画像，不读取旧画像。
2. 无旧画像时直接保存 Step 1 结果，不再触发 Step 2。
3. 有旧画像时会进入合并步骤，且合并结果遵守“冲突新信息优先、去重、空字段保留旧值”。
4. 合并失败时降级保存 Step 1 结果，而不是整个流程失败。

建议新增测试名：

```python
def test_form_memory_uses_fast_path_when_no_existing_profile(): ...
def test_form_memory_merges_when_existing_profile_exists(): ...
def test_form_memory_falls_back_to_extract_result_when_merge_fails(): ...
def test_extract_and_merge_retry_are_independent(): ...
```

示例断言风格：

```python
assert db.save_profile.await_args.args[1] == result["portrait_text"]
assert queue.submit.await_count == 1  # fast path
assert queue.submit.await_count == 2  # existing profile path: extract + merge
assert "冲突" not in merged_portrait["confirmed"]["identity"]
assert "旧值" 保留在 merged 结果中
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -k "fast_path or merge or retry" -v`

Expected: FAIL，当前 `form_memory()` 仍是单步 prompt，无法满足上述断言。

**Step 3: Write minimal implementation**

先不要改主逻辑，只补最小测试支架所需的 fixture / mock 结构，确保测试清楚表达两步式契约。若现有测试里有重复的 LLM mock 数据，可以直接复用，不新增额外测试框架。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -k "fast_path or merge or retry" -v`

Expected: 先仍然 FAIL，直到 Task 3 落地实现。
---

### Task 3: 将 MemoryManager 重构为提取 + 合并两步

**Files:**
- Modify: `ai_end/src/chat/memory_manager.py`
- Modify: `ai_end/tests/unit/test_memory_manager.py`

**Step 1: Write the failing test**

如果 Task 2 还没把断言写全，这里先补最后缺失的行为测试，确保实现前能完整覆盖：

```python
async def test_load_existing_profile_returns_empty_when_profile_invalid(): ...
async def test_merge_path_uses_existing_profile_json_and_new_extract_json(): ...
```

重点验证：
- 已保存画像是 v1 或非法 JSON 时，应被视为“无旧画像”，走首版快速路径。
- `_adjudicate_identity()` 和 `_validate_v2_memory_schema()` 继续复用，不要复制一份新校验器。

**Step 2: Run test to verify it fails**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -v`

Expected: FAIL，明确指出 `form_memory()` 仍没有拆为 extract/merge 两步。

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/memory_manager.py` 做最小重构，保持公共返回契约不变：

```python
async def form_memory(self, messages):
    extracted = await self._extract_portrait(messages)
    if not extracted["portrait_text"] and not extracted["knowledge_text"]:
        return self._failure_or_retry_result(...)

    existing_profile = await self._load_existing_profile()
    if not existing_profile:
        await self.memory_db.save_profile(self.user_id, extracted["portrait_text"], extracted["knowledge_text"])
        return success_result

    merged = await self._merge_portraits(existing_profile, extracted)
    if merged is None:
        await self.memory_db.save_profile(self.user_id, extracted["portrait_text"], extracted["knowledge_text"])
        return success_result_for_extract

    await self.memory_db.save_profile(self.user_id, merged["portrait_text"], merged["knowledge_text"])
    return success_result_for_merge
```

同时新增/拆分以下内部方法：

```python
async def _extract_portrait(self, messages): ...
async def _merge_portraits(self, existing_profile: str, extracted: dict[str, str]): ...
async def _build_extract_prompt(self, messages): ...
async def _build_merge_prompt(self, existing_profile: str, extracted: dict[str, str]): ...
```

实现要求：
- Step 1 的 prompt 只包含当前对话。
- Step 2 的 prompt 只包含旧画像 JSON + 新画像 JSON。
- `_parse_memory()` 继续作为唯一解析入口。
- `_build_memory_prompt()` 和 `_build_retry_prompt()` 可以保留兼容，但主流程不再调用。
- Step 1 / Step 2 的重试各自独立，最多 3 次。
- Step 2 失败时，降级保存 Step 1 结果。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -v`

Expected: PASS，或者仅有与本次变更无关的既有失败；本任务范围内的 memory tests 应全部通过。

---

### Task 4: 为端到端画像流补回归测试

**Files:**
- Modify: `ai_end/tests/integration/test_profile_integration.py`
- Modify: `ai_end/tests/unit/test_memory_chat.py`
- Modify: `ai_end/tests/unit/test_handlers.py`

**Step 1: Write the failing test**

补 3 个回归点：

1. `ChatClient.form_memory()` 仍然只是入口包装，调用时不改变外部协议。
2. `handle_form_memory()` 在真实调用链下仍能拿到两步式 MemoryManager 的返回值。
3. `step1 成功 + step2 失败` 时，最终仍会保存 Step 1 结果。

建议在 `test_profile_integration.py` 新增：

```python
async def test_form_memory_fast_path_skips_merge_when_no_profile(): ...
async def test_form_memory_merge_path_uses_two_llm_calls(): ...
async def test_form_memory_merge_failure_falls_back_to_extract_result(): ...
```

必要时在 `test_memory_chat.py` 或 `test_handlers.py` 中增加一个最小包装测试，确认调用方不用改签名。

**Step 2: Run test to verify it fails**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py tests/unit/test_memory_chat.py tests/unit/test_handlers.py -k memory -v`

Expected: FAIL，提示旧实现没有两步式 fast path / fallback 行为。

**Step 3: Write minimal implementation**

优先只改测试，不再新增业务代码；如果发现调用链里有与 `MemoryManager` 新返回值不兼容的旧断言，再最小调整断言而不是新增兼容分支。

**Step 4: Run test to verify it passes**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py tests/unit/test_memory_chat.py tests/unit/test_handlers.py -k memory -v`

Expected: PASS。

---

### Task 5: 做最终回归与收尾验证

**Files:**
- Test: `ai_end/tests/unit/test_prompts_runtime.py`
- Test: `ai_end/tests/unit/test_memory_manager.py`
- Test: `ai_end/tests/integration/test_profile_integration.py`

**Step 1: Run the focused memory test set**

Run:

```bash
cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py tests/unit/test_memory_manager.py tests/integration/test_profile_integration.py -v
```

Expected: 全部 PASS；如有跳过项，只能是数据库或外部依赖导致的既有 skip，不能是新增失败。

**Step 2: Run the broader ai_end regression slice**

Run:

```bash
cd ai_end && uv run pytest tests/unit -k "memory or prompt" -v
```

Expected: PASS。

**Step 3: Inspect diffs and confirm no schema / caller drift**

确认最终没有改动：
- 数据库 schema
- `ChatClient.form_memory()` 的调用方式
- `MemoryDB.save_profile()` 签名
- 现有画像摘要注入逻辑

---

## 交付结论

完成后，`form_memory()` 的行为应变为：
- 无旧画像时，直接保存 Step 1 提取结果。
- 有旧画像时，先提取新画像，再与旧画像合并。
- Step 1 失败仍保持现有降级逻辑。
- Step 2 失败时，回退保存 Step 1 结果。
- 调用方无感知，数据库结构不变。

## 执行选择

Plan complete and saved to `docs/plans/2026-04-13-memory-two-step-portrait-implementation-plan.md`. Two execution options:

1. Subagent-Driven（本会话）- 我分任务派发新的 subagent，每个任务后复核，迭代更快。
2. Parallel Session（单独会话）- 你在新会话里使用 `executing-plans` 按计划批量推进，并在检查点汇报。

如果你要继续，我建议选 1，技术债更低，回收更快。