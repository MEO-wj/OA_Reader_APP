# TodoList 强制执行框架实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增 todolist 技能，作为 LLM 每次对话的强制执行框架，通过硬打回机制确保步骤不被跳过。

**Architecture:** todolist 作为一级工具（技能入口），包含二级工具 `todolist_check`。`todolist_handler.py` 实现无状态检查点校验，不合法跳过时返回错误信息触发 LLM 重新执行。通过在 `handlers.py` 的模块映射中新增一行实现集成。

**Tech Stack:** Python 3.11+, pytest, YAML (SKILL.md/TOOLS.md)

**Design doc:** `docs/plans/2026-04-12-todolist-framework-design.md`

---

### Task 1: todolist_handler 单元测试

**Files:**
- Create: `ai_end/tests/unit/test_todolist_handler.py`

**Step 1: 编写全部失败测试**

```python
"""
测试 src.core.todolist_handler - 任务步骤检查点
"""
import pytest
import asyncio

from src.core.todolist_handler import check_step, _is_valid_skip_reason


class TestIsValidSkipReason:
    """测试跳过理由校验"""

    def test_empty_reason_is_invalid(self):
        assert _is_valid_skip_reason("") is False

    def test_none_reason_is_invalid(self):
        assert _is_valid_skip_reason(None) is False

    def test_whitespace_only_is_invalid(self):
        assert _is_valid_skip_reason("   ") is False

    def test_short_reason_under_5_chars_is_invalid(self):
        assert _is_valid_skip_reason("无") is False

    def test_reason_exactly_5_chars_is_valid(self):
        assert _is_valid_skip_reason("不需要") is False  # 3个字 < 5

    def test_reason_5_chars_is_valid(self):
        assert _is_valid_skip_reason("用户只是简单问候无需记忆") is True

    def test_long_reason_is_valid(self):
        assert _is_valid_skip_reason("用户只是在打招呼，没有提供任何个人信息") is True


class TestCheckStepStep1:
    """测试步骤1（判断是否保存记忆）"""

    @pytest.mark.asyncio
    async def test_step1_done_passes(self):
        result = await check_step(step=1, status="done")
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_valid_reason_passes(self):
        result = await check_step(step=1, status="skip", reason="用户只是打招呼，没有提供任何个人信息")
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_empty_reason_rejected(self):
        result = await check_step(step=1, status="skip", reason="")
        assert result["success"] is False
        assert "error" in result
        assert "步骤1" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_short_reason_rejected(self):
        result = await check_step(step=1, status="skip", reason="无")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_step1_start_passes(self):
        result = await check_step(step=1, status="start")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_step1_done_without_reason_passes(self):
        """status=done 时不需要 reason"""
        result = await check_step(step=1, status="done")
        assert result["success"] is True


class TestCheckStepStep2:
    """测试步骤2（判断是否需要查询文章）"""

    @pytest.mark.asyncio
    async def test_step2_done_passes(self):
        result = await check_step(step=2, status="done")
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_valid_reason_passes(self):
        result = await check_step(step=2, status="skip", reason="用户问题与OA文章无关，不需要查询")
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_empty_reason_rejected(self):
        result = await check_step(step=2, status="skip", reason="")
        assert result["success"] is False
        assert "error" in result
        assert "步骤2" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_short_reason_rejected(self):
        result = await check_step(step=2, status="skip", reason="跳过")
        assert result["success"] is False


class TestCheckStepStep3:
    """测试步骤3（整理并总结回答）"""

    @pytest.mark.asyncio
    async def test_step3_always_passes(self):
        result = await check_step(step=3, status="done")
        assert result["success"] is True
        assert "最终回答" in result["message"]

    @pytest.mark.asyncio
    async def test_step3_with_skip_also_passes(self):
        """步骤3 无论什么状态都通过"""
        result = await check_step(step=3, status="skip")
        assert result["success"] is True


class TestCheckStepEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_invalid_step_returns_generic_success(self):
        """未定义的步骤号返回成功（向前兼容）"""
        result = await check_step(step=99, status="done")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reason_with_only_whitespace_treated_as_empty(self):
        result = await check_step(step=1, status="skip", reason="   ")
        assert result["success"] is False
```

**Step 2: 运行测试确认全部失败**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.core.todolist_handler'`）

---

### Task 2: todolist_handler 实现

**Files:**
- Create: `ai_end/src/core/todolist_handler.py`

**Step 1: 编写最小实现**

```python
"""
任务步骤检查点处理器 - 校验 todolist 各步骤完成情况
"""


async def check_step(step: int, status: str, reason: str = "") -> dict:
    """
    任务步骤检查点。校验步骤完成情况，不合规则返回错误触发打回。

    Args:
        step: 当前步骤编号 (1, 2, 3)
        status: 步骤状态 (done, skip, start)
        reason: 跳过步骤时的理由（status=skip 时必填）

    Returns:
        success=True: 步骤通过，message 包含下一步指引
        success=False: 步骤被打回，error 包含打回原因
    """
    if step == 1:
        if status == "skip" and not _is_valid_skip_reason(reason):
            return {
                "success": False,
                "error": f"步骤1跳过理由不合理：'{reason}'。请重新判断是否需要保存记忆。",
            }
        return {"success": True, "message": "步骤1完成。请继续步骤2：判断是否需要查询文章。"}

    if step == 2:
        if status == "skip" and not _is_valid_skip_reason(reason):
            return {
                "success": False,
                "error": f"步骤2跳过理由不合理：'{reason}'。请重新判断是否需要查询文章。",
            }
        return {"success": True, "message": "步骤2完成。请继续步骤3：整理并总结回答。"}

    if step == 3:
        return {"success": True, "message": "请直接输出最终回答。"}

    # 未定义的步骤号：向前兼容，默认通过
    return {"success": True, "message": "请继续下一步。"}


def _is_valid_skip_reason(reason: str) -> bool:
    """校验跳过理由是否充分：不能为空，不能是无意义的短文本（至少5字符）。"""
    if not reason or len(reason.strip()) < 5:
        return False
    return True
```

**Step 2: 运行测试确认全部通过**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: 全部 PASS

---

### Task 3: todolist SKILL.md 技能定义

**Files:**
- Create: `ai_end/skills/todolist/SKILL.md`

**Step 1: 创建技能定义文件**

```markdown
---
name: todolist
description: 任务执行检查点框架。每次对话必须先调用此技能，按步骤完成：1.判断保存记忆 2.判断查询文章 3.总结回答。不可跳过步骤。
verification_token: TODOLIST-FRAMEWORK-2026
---

# 任务执行框架

你必须按以下步骤顺序完成每次对话任务。**严格按顺序执行，不可跳过任何步骤。**

## 步骤 1：判断是否需要保存记忆

- 如果用户分享了个人信息、偏好、知识或表达了明确的意图 → 调用 `form_memory` 工具执行记忆保存
- 如果用户只是在闲聊、打招呼、或没有提供有价值的信息 → 调用 `todolist_check`，传入 `step=1, status=skip, reason="..."`，**reason 必须充分具体**（至少5个字符）
- 执行完成后调用 `todolist_check`，传入 `step=1, status=done`
- **不得直接跳过此步骤，必须给出判断**

## 步骤 2：判断是否需要查询文章

- 如果用户问题与 OA 文章/通知/公告相关 → 调用 `article-retrieval` 技能，然后使用 `search_articles` / `grep_article` 查询
- 如果用户问题与 OA 文章无关 → 调用 `todolist_check`，传入 `step=2, status=skip, reason="..."`，**reason 必须充分具体**
- 查询完成后调用 `todolist_check`，传入 `step=2, status=done`
- **不得直接跳过此步骤，必须给出判断**

## 步骤 3：整理并总结回答

- 综合前两步的结果，生成最终回答
- 无需调用任何工具，直接输出即可
- 回答应引用来源（如有文章数据）

## 跳过规则

- 跳过步骤时**必须**提供 `reason` 参数
- `reason` 至少需要 5 个字符，解释为什么该步骤不适用
- 如果理由不充分，`todolist_check` 会返回错误，你必须重新判断
- 不要用"无"、"跳过"、"不需要"等过短理由

## 输出风格

- 步骤推进过程不暴露给用户
- 最终回答直接呈现结果，不提及 todolist、步骤编号等内部机制
```

**Step 2: 验证 YAML front matter 可解析**

Run: `cd ai_end && python -c "import yaml; data = yaml.safe_load(open('skills/todolist/SKILL.md').read().split('---\n')[1].split('---')[0]); print(data['name'], data['description'])"`
Expected: 输出 `todolist 任务执行检查点框架...`

---

### Task 4: todolist TOOLS.md 工具定义

**Files:**
- Create: `ai_end/skills/todolist/TOOLS.md`

**Step 1: 创建工具定义文件**

```yaml
tools:
  - name: todolist_check
    description: |
      任务步骤检查点。每完成一个步骤后必须调用此工具报告进度。
      如果跳过步骤，必须提供合理理由（至少5个字符），否则将被打回。
    parameters:
      type: object
      properties:
        step:
          type: integer
          enum: [1, 2, 3]
          description: 当前步骤编号
        status:
          type: string
          enum: [done, skip, start]
          description: "done=完成, skip=跳过(需提供reason), start=开始执行"
        reason:
          type: string
          description: 跳过步骤时的理由（status=skip 时必填，至少5个字符）
      required: [step, status]
    handler: todolist_handler.check_step
```

**Step 2: 验证 YAML 格式和 handler 路径**

Run: `cd ai_end && python -c "import yaml; data = yaml.safe_load(open('skills/todolist/TOOLS.md')); print(data['tools'][0]['name'], data['tools'][0]['handler'])"`
Expected: 输出 `todolist_check todolist_handler.check_step`

---

### Task 5: handlers.py 模块映射集成

**Files:**
- Modify: `ai_end/src/chat/handlers.py:98-100`

**Step 1: 在 module_mappings 字典中新增一行**

在 `ai_end/src/chat/handlers.py` 第 98-100 行的 `module_mappings` 字典中新增：

```python
module_mappings = {
    "article_retrieval": "src.core.article_retrieval",
    "todolist_handler": "src.core.todolist_handler",  # 新增
}
```

**Step 2: 验证集成 — todolist_check 通过 handlers 分发可达**

```python
# 测试 todolist_check 作为二级工具能被正确分发
def test_todolist_check_dispatched_through_handlers():
    """todolist_check 应通过 _dispatch_secondary_tool 正确分发到 todolist_handler.check_step"""
    # 这个测试验证 module_mappings 包含 todolist_handler
    import importlib
    from src.chat.handlers import _dispatch_secondary_tool
    # 验证模块可以被导入
    mod = importlib.import_module("src.core.todolist_handler")
    assert hasattr(mod, "check_step")
```

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: 全部 PASS

---

### Task 6: 集成测试 — todolist_check 通过 handle_tool_calls 完整流程

**Files:**
- Modify: `ai_end/tests/unit/test_todolist_handler.py`

**Step 1: 编写集成测试**

在 `test_todolist_handler.py` 末尾追加：

```python
class TestTodolistCheckIntegration:
    """测试 todolist_check 通过 handle_tool_calls 完整调用链"""

    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_through_handle_tool_calls(self):
        """todolist_check(step=1, status=done) 应通过 handle_tool_calls 正确返回成功"""
        from unittest.mock import Mock, patch
        from src.chat.handlers import handle_tool_calls
        from src.core.skill_parser import SkillInfo

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "todolist": SkillInfo(
                name="todolist",
                description="任务执行框架",
                content="",
                verification_token="TODOLIST-FRAMEWORK-2026",
            )
        }
        # 设置 secondary_tools 模拟 todolist 技能激活后的工具列表
        mock_skill_system.available_skills["todolist"].secondary_tools = [
            {
                "name": "todolist_check",
                "handler": "todolist_handler.check_step",
            }
        ]

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_1"

        result = await handle_tool_calls(
            [mock_tool_call],
            mock_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is True
        assert "步骤2" in data["message"]

    @pytest.mark.asyncio
    async def test_todolist_check_step1_skip_invalid_rejected_through_handle_tool_calls(self):
        """todolist_check(step=1, status=skip, reason="无") 应被拒绝"""
        from unittest.mock import Mock
        from src.chat.handlers import handle_tool_calls
        from src.core.skill_parser import SkillInfo

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "todolist": SkillInfo(
                name="todolist",
                description="任务执行框架",
                content="",
                verification_token="TODOLIST-FRAMEWORK-2026",
            )
        }
        mock_skill_system.available_skills["todolist"].secondary_tools = [
            {
                "name": "todolist_check",
                "handler": "todolist_handler.check_step",
            }
        ]

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "skip", "reason": "无"}'
        mock_tool_call.id = "call_tl_2"

        result = await handle_tool_calls(
            [mock_tool_call],
            mock_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is False
        assert "error" in data
```

**Step 2: 运行全部 todolist 测试**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: 全部 PASS

---

### Task 7: 全量回归测试

**Step 1: 运行全部单元测试确认无回归**

Run: `cd ai_end && uv run pytest tests/unit/ -v`
Expected: 全部 PASS，无新增失败

**Step 2: 验证现有 handlers 测试无回归**

Run: `cd ai_end && uv run pytest tests/unit/test_handlers.py -v`
Expected: 全部 PASS
