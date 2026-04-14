# Code Review 问题修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成代码审查文档中 C1/C2/C3、I1/I2/I4/I5、M1/M2/M3/M4 的最小化修复，并保持行为兼容与技术债不增长。

**Architecture:** 采用最小变更路径：先写失败测试，再做针对性实现，再跑聚焦测试回归。核心改动集中在 `MemoryManager`（删除死代码、修复重试提示、返回契约一致性）与 `todolist_handler`（状态白名单校验、done 校验函数去冗余参数）；文档与提示词仅做约束增强，不引入新流程。全程遵循 DRY/YAGNI，避免扩散式重构。

**Tech Stack:** Python 3.11+, pytest, FastAPI 代码结构, Markdown (SKILL.md)

**Design doc:** `docs/plans/2026-04-14-code-review-fixes-design.md`

**Skill References:** @superpowers:test-driven-development @superpowers:verification-before-completion

---

### Task 1: 删除 MEMORY_PROMPT_TEMPLATE 依赖链（先写失败测试）

**Files:**
- Modify: `ai_end/tests/unit/test_prompts_runtime.py:1-160`
- Modify: `ai_end/tests/prompts_test_constants.py:1-40`
- Modify: `ai_end/tests/unit/test_memory_manager.py:1-260`

**Step 1: 修改 prompts_runtime 单测，移除 MEMORY_PROMPT_TEMPLATE 断言**

将 `test_runtime_prompt_constants_exist` 的 `required` 列表改为：

```python
required = [
    "SYSTEM_PROMPT_TEMPLATE",
    "COMPACT_PROMPT_TEMPLATE",
    "TITLE_PROMPT_TEMPLATE",
    "DOC_SUMMARY_SYSTEM_PROMPT",
    "DOC_SUMMARY_USER_PROMPT_TEMPLATE",
    "READ_REFERENCE_TOOL_DESCRIPTION",
    "PORTRAIT_EXTRACT_PROMPT",
    "PORTRAIT_MERGE_PROMPT",
]
```

并删除以下测试函数：

```python
def test_memory_prompt_contains_v2_fields():
    ...

def test_memory_prompt_contains_identity_constraint():
    ...

def test_memory_prompt_contains_existing_profile_placeholder():
    ...

def test_memory_prompt_contains_merge_and_conflict_rules():
    ...

def test_memory_prompt_contains_confirmed_interests_threshold():
    ...

def test_memory_prompt_still_exists_for_compatibility():
    ...
```

**Step 2: 修改 prompts_test_constants，删除仅供 MEMORY_PROMPT_TEMPLATE 的常量**

删除：

```python
MEMORY_V2_REQUIRED_FIELDS = [...]
MEMORY_V2_REQUIRED_CONSTRAINTS = [...]
```

并同步删除 `test_prompts_runtime.py` 中对应 import：

```python
from tests.prompts_test_constants import (
    SYSTEM_PROMPT_EXPECTED_PHRASES,
    COMPACT_PROMPT_EXPECTED_PHRASES,
    COMPACT_V2_NO_MERGE_CONSTRAINTS,
    SYSTEM_PROMPT_V2_CONSTRAINTS,
    PORTRAIT_EXTRACT_REQUIRED_PHRASES,
    PORTRAIT_MERGE_REQUIRED_PHRASES,
)
```

**Step 3: 删除 memory_manager 单测中对旧模板的源码检查测试**

删除函数：

```python
def test_memory_prompt_uses_runtime_template(self):
    ...
```

并移除顶部未使用导入：

```python
from src.chat.prompts_runtime import PORTRAIT_EXTRACT_PROMPT, PORTRAIT_MERGE_PROMPT
```

**Step 4: 运行测试确认当前为失败（RED）**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py tests/unit/test_memory_manager.py -v`
Expected: FAIL（实现层仍引用 `MEMORY_PROMPT_TEMPLATE`，会出现 ImportError/AssertionError）

---

### Task 2: MemoryManager 返回契约与死代码清理（实现）

**Files:**
- Modify: `ai_end/src/chat/memory_manager.py:8,150-273,317-383`

**Step 1: 移除 MEMORY_PROMPT_TEMPLATE 导入与死代码方法**

将导入改为：

```python
from src.chat.prompts_runtime import PORTRAIT_EXTRACT_PROMPT, PORTRAIT_MERGE_PROMPT
```

删除以下方法：

```python
async def _build_memory_prompt(self, messages: list[dict[str, Any]]) -> str:
    ...

async def _load_existing_profile(self) -> str:
    ...

def _build_retry_prompt(self, messages: list[dict[str, Any]], last_error: str) -> str:
    ...
```

**Step 2: 修复 `_merge_portraits` 返回注解与注释一致性（C1）**

函数签名改为：

```python
async def _merge_portraits(
    self, existing_profile: dict[str, str], extracted: dict[str, Any],
) -> dict[str, Any]:
```

docstring 末尾改为：

```python
全部重试失败返回空结果：portrait_text/knowledge_text 为空串。
```

**Step 3: 在 `_extract_portrait` 重试 prompt 追加上次错误信息（I5）**

将循环内 prompt 构造改为：

```python
prompt = PORTRAIT_EXTRACT_PROMPT.format(conversation=conversation)
if attempt > 1 and last_error:
    prompt = (
        f"{prompt}\n\n"
        f"【上次错误】{last_error}\n"
        "请严格输出合法 v2 JSON，不要添加任何额外文本。"
    )
```

并在解析失败后保持：

```python
last_error = f"第{attempt}次尝试: LLM 返回内容无法解析为有效 v2 JSON"
```

**Step 4: 运行相关单测确认通过（GREEN）**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -v`
Expected: PASS（尤其重试与两步流程测试通过）

---

### Task 3: 为 I5 增加重试错误透传测试（先 RED 后 GREEN）

**Files:**
- Modify: `ai_end/tests/unit/test_memory_manager.py:542-620`

**Step 1: 新增失败测试，断言第二次 prompt 含“上次错误”**

在 `TestRetryProtocol` 中追加：

```python
@pytest.mark.asyncio
async def test_retry_prompt_contains_previous_error_message(self):
    uid = "00000000-0000-0000-0008-000000000205"
    queue = MagicMock()
    captured_prompts: list[str] = []

    async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
        captured_prompts.append(prompt)
        if len(captured_prompts) == 1:
            return self._invalid_response()
        return self._valid_v2_response()

    queue.submit = AsyncMock(side_effect=capture_submit)
    db = MagicMock()
    db.save_profile = AsyncMock()
    db.get_profile = AsyncMock(return_value=None)

    with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
        manager = MemoryManager(user_id=uid, memory_db=db)
        result = await manager.form_memory([{"role": "user", "content": "你好"}])

    assert result["saved"] is True
    assert len(captured_prompts) == 2
    retry_prompt = captured_prompts[1]
    assert "上次错误" in retry_prompt
    assert "第1次尝试" in retry_prompt
```

**Step 2: 先单独运行该用例确认 RED**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_retry_prompt_contains_previous_error_message -v`
Expected: FAIL（当前重试 prompt 尚未包含错误信息时）

**Step 3: 应用 Task 2 的实现后再运行同一用例**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol::test_retry_prompt_contains_previous_error_message -v`
Expected: PASS

**Step 4: 运行 TestRetryProtocol 全量回归**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py::TestRetryProtocol -v`
Expected: PASS

---

### Task 4: prompts_runtime 删除旧常量并补充误判约束（实现）

**Files:**
- Modify: `ai_end/src/chat/prompts_runtime.py:62-111`
- Modify: `ai_end/tests/unit/test_prompts_runtime.py:1-160`

**Step 1: 删除 `MEMORY_PROMPT_TEMPLATE` 常量整段（I1/I2）**

直接移除：

```python
# MEMORY_PROMPT_TEMPLATE 输出 JSON 格式，供程序解析
MEMORY_PROMPT_TEMPLATE = """..."""
```

保留并继续使用：
- `PORTRAIT_EXTRACT_PROMPT`
- `PORTRAIT_MERGE_PROMPT`

**Step 2: 在 `PORTRAIT_EXTRACT_PROMPT` 的分层规则增加防误判约束（M4）**

将 confirmed 规则更新为：

```text
- confirmed: 用户明确陈述或已验证的事实；禁止将未经验证的行为推断写入 confirmed（例如“频繁阅读某类文章”仅可进入 hypothesized）
```

**Step 3: 新增/更新提示词测试断言该约束存在**

在 `test_portrait_extract_prompt_exists_and_blocks_merge_behavior` 所依赖常量中新增短语，例如：

```python
PORTRAIT_EXTRACT_REQUIRED_PHRASES = [
    "仅基于对话内容提取",
    "不参考旧画像",
    "禁止将未经验证的行为推断写入 confirmed",
    "confirmed",
    "hypothesized",
    "knowledge",
]
```

**Step 4: 运行 prompts 相关测试**

Run: `cd ai_end && uv run pytest tests/unit/test_prompts_runtime.py -v`
Expected: PASS

---

### Task 5: 修复集成测试重复常量与文件尾换行（C2/C3）

**Files:**
- Modify: `ai_end/tests/integration/test_profile_integration.py:94-102`
- Modify: `ai_end/tests/unit/test_memory_manager.py` (文件末尾换行)

**Step 1: 删除第二个 `SAMPLE_CONVERSATION` 重复定义块**

删除重复段：

```python
# 测试用的模拟对话数据
SAMPLE_CONVERSATION = [
    ...
]
```

保留文件顶部首次定义（约第 23 行）。

**Step 2: 为 `test_memory_manager.py` 文件末尾补充单个换行符**

确保文件以 `\n` 结尾（POSIX/编辑器通用规范）。

**Step 3: 运行目标测试文件确认通过**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py -v`
Expected: PASS（至少不再出现重复定义引发的覆盖风险）

**Step 4: 运行格式与语法快速检查**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py -q`
Expected: PASS

---

### Task 6: todolist status 非法值校验（先 RED）

**Files:**
- Modify: `ai_end/tests/unit/test_todolist_handler.py`

**Step 1: 在边界测试中新增非法状态用例**

追加：

```python
@pytest.mark.asyncio
async def test_invalid_status_rejected(self):
    result = await check_step(step=1, status="invalid", called_tools=[])
    assert result["success"] is False
    assert "status" in result["error"]
```

**Step 2: 增加 step=2 非法状态覆盖**

```python
@pytest.mark.asyncio
async def test_step2_invalid_status_rejected(self):
    result = await check_step(step=2, status="oops", called_tools=[])
    assert result["success"] is False
    assert "status" in result["error"]
```

**Step 3: 运行对应测试确认 RED**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py::TestCheckStepEdgeCases -v`
Expected: FAIL（当前实现对非法 status 默认放行）

**Step 4: 记录失败信息关键词**

Expected fail contains: `assert True is False`（或 message 未包含 status 错误）

---

### Task 7: todolist_handler 实现 status 白名单 + `_validate_done` 去冗余（GREEN）

**Files:**
- Modify: `ai_end/src/core/todolist_handler.py:6-90`

**Step 1: 增加状态白名单并在 `check_step` 开头校验（I4）**

新增常量：

```python
VALID_STATUSES = {"start", "done", "skip"}
```

在 `called_tools` 校验之后添加：

```python
if status not in VALID_STATUSES:
    return {
        "success": False,
        "error": f"步骤{step}状态非法：'{status}'。允许值仅为 start/done/skip。",
    }
```

**Step 2: `_validate_done` 去掉 `tool_desc` 参数，从 `REQUIRED_TOOLS[step]` 自动生成（M1）**

函数签名改为：

```python
def _validate_done(
    step: int,
    called_tools: list[str],
    action_desc: str,
    next_hint: str,
    reason: str = "",
) -> dict:
```

错误文本中工具描述改为：

```python
tool_desc = "/".join(sorted(required)) if required else "必需工具"
```

并使用：

```python
"error": f"步骤{step}要求调用{tool_desc}工具，但未检测到调用记录。请先执行{action_desc}再标记完成。"
```

**Step 3: 更新 `check_step` 中两处 `_validate_done(...)` 调用参数**

步骤1改为：

```python
return _validate_done(step, called_tools, "保存记忆", "请继续步骤2：判断是否需要查询文章。", reason)
```

步骤2改为：

```python
return _validate_done(step, called_tools, "查询文章", "请继续步骤3：整理并总结回答。", reason)
```

**Step 4: 运行 todolist 全量单测**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: PASS

---

### Task 8: handlers 注释改进与 TODO 说明（I3 + M2）

**Files:**
- Modify: `ai_end/src/chat/handlers.py:160,207-209`

**Step 1: 为 `processed_tools` 增加语义注释（M2）**

将定义改为：

```python
# 已尝试处理过的工具（不代表调用成功），用于 todolist_check 进行步骤校验。
processed_tools: list[str] = []
```

**Step 2: 在 `todolist_check` 注入处补充 TODO（I3，保持现状）**

在注入处上方加入：

```python
# TODO(tech-debt): 当前仅注入本批次已尝试工具；未来若引入跨回合校验，
# 可扩展为“本回合窗口 + 持久化轨迹”联合判定，避免误报/漏报。
if function_name == "todolist_check":
    function_args["called_tools"] = list(processed_tools)
```

**Step 3: 运行 handlers 关联回归**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py::TestTodolistCheckIntegration -v`
Expected: PASS

**Step 4: 运行静态检查（若项目已有）**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -q`
Expected: PASS

---

### Task 9: 更新 todolist 技能文档步骤 1 示例（M3）

**Files:**
- Modify: `ai_end/skills/todolist/SKILL.md`

**Step 1: 在步骤 1 增加“触发/不触发”示例**

补充以下文案（紧跟步骤 1 规则后）：

```markdown
- 触发示例：
  - 用户说“我是临床医学专硕，想留在北京发展” → 应调用 form_memory 再标记 done
  - 用户说“我英语六级 550，倾向消化内科” → 应调用 form_memory 再标记 done
- 不触发示例：
  - 用户仅说“你好”“在吗” → 应 skip，并提供充分 reason
  - 用户只问“今天天气怎样”且无个人信息 → 应 skip，并提供充分 reason
```

**Step 2: 保持步骤顺序与校验规则不变**

确认不修改以下核心句：

```markdown
- 先调用 todolist_check(step=1, status=start)
- done 会校验 form_memory 是否真实调用
- skip 必须包含充分 reason
```

**Step 3: 运行与技能流程相关测试**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py::TestTodolistCheckIntegration -v`
Expected: PASS

**Step 4: 人工校对 SKILL 文案一致性**

Check:
- 步骤编号与 tool 名不变
- 不引入与实现冲突的新约束

---

### Task 10: 全量回归验证与完成检查（不含提交）

**Files:**
- Verify only (no code changes)

**Step 1: 运行本次受影响单测集合**

Run: `cd ai_end && uv run pytest tests/unit/test_memory_manager.py tests/unit/test_prompts_runtime.py tests/unit/test_todolist_handler.py -v`
Expected: PASS

**Step 2: 运行受影响集成测试**

Run: `cd ai_end && uv run pytest tests/integration/test_profile_integration.py -v`
Expected: PASS

**Step 3: 运行一次高层回归（可选但建议）**

Run: `cd ai_end && uv run pytest tests/unit tests/integration -q`
Expected: PASS 或仅存在与本任务无关的已知失败

**Step 4: 输出变更摘要（不提交代码）**

记录：
- 每个问题编号（C1~M4）对应文件与测试证据
- 未处理项：M5（无需变更）
- 说明：本实施计划按要求不包含 git commit 步骤
