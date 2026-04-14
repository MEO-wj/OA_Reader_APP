# Todolist Start 标签 + 工具调用校验 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 todolist 框架增加 `start` 占位标签和 `done` 时的工具调用校验，防止 LLM 未调用必需工具就谎报完成。

**Architecture:** `check_step` 新增 `called_tools` 参数（必填），由 `handlers.py` 在分发 `todolist_check` 时自动注入当轮已处理的工具名列表。handler 内查表 `REQUIRED_TOOLS` 校验是否包含必需工具，缺失则打回。`called_tools` 为空列表时同样打回，不预留兼容出口。

**Tech Stack:** Python 3.11+, pytest, YAML (SKILL.md/TOOLS.md)

**Design doc:** `docs/plans/2026-04-14-todolist-start-and-tool-verification-design.md`

---

### Task 1: todolist_handler 工具校验 — 失败测试

**Files:**
- Modify: `ai_end/tests/unit/test_todolist_handler.py`

**Step 1: 在 TestCheckStepStep1 中新增 done 校验失败测试**

在 `test_step1_done_without_reason_passes` 之后追加：

```python
    @pytest.mark.asyncio
    async def test_step1_done_without_form_memory_rejected(self):
        """status=done 但 called_tools 中无 form_memory 应被打回"""
        result = await check_step(step=1, status="done", called_tools=["todolist_check"])
        assert result["success"] is False
        assert "error" in result
        assert "form_memory" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_done_with_form_memory_passes(self):
        """status=done 且 called_tools 中有 form_memory 应通过"""
        result = await check_step(step=1, status="done", called_tools=["form_memory", "todolist_check"])
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_done_with_empty_called_tools_rejected(self):
        """status=done 但 called_tools 为空列表应被打回"""
        result = await check_step(step=1, status="done", called_tools=[])
        assert result["success"] is False
        assert "form_memory" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_done_with_reason_includes_reason_in_message(self):
        """status=done 且有 reason 时 message 应附带 reason"""
        result = await check_step(step=1, status="done", called_tools=["form_memory"], reason="用户分享了专业信息")
        assert result["success"] is True
        assert "备注" in result["message"]
        assert "用户分享了专业信息" in result["message"]
```

**Step 2: 在 TestCheckStepStep2 中新增 done 校验失败测试**

在 `test_step2_skip_with_short_reason_rejected` 之后追加：

```python
    @pytest.mark.asyncio
    async def test_step2_done_without_search_tool_rejected(self):
        """status=done 但 called_tools 中无搜索工具应被打回"""
        result = await check_step(step=2, status="done", called_tools=["todolist_check"])
        assert result["success"] is False
        assert "error" in result
        assert "search_articles" in result["error"] or "grep_article" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_done_with_search_articles_passes(self):
        """status=done 且 called_tools 中有 search_articles 应通过"""
        result = await check_step(step=2, status="done", called_tools=["search_articles"])
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_done_with_grep_article_passes(self):
        """status=done 且 called_tools 中有 grep_article 应通过"""
        result = await check_step(step=2, status="done", called_tools=["grep_article"])
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_done_with_empty_called_tools_rejected(self):
        """status=done 但 called_tools 为空列表应被打回"""
        result = await check_step(step=2, status="done", called_tools=[])
        assert result["success"] is False
```

**Step 3: 修改现有 done 测试传入 called_tools**

将 `TestCheckStepStep1.test_step1_done_passes` 和 `TestCheckStepStep2.test_step2_done_passes` 改为传入 `called_tools`（否则会因为缺少必填参数而报 TypeError）：

```python
    @pytest.mark.asyncio
    async def test_step1_done_passes(self):
        result = await check_step(step=1, status="done", called_tools=["form_memory"])
        assert result["success"] is True
        assert "步骤2" in result["message"]
```

```python
    @pytest.mark.asyncio
    async def test_step2_done_passes(self):
        result = await check_step(step=2, status="done", called_tools=["search_articles"])
        assert result["success"] is True
        assert "步骤3" in result["message"]
```

**Step 4: 运行测试确认失败**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: FAIL（`check_step() missing 1 required keyword-only argument: 'called_tools'` 或 TypeError）

---

### Task 2: todolist_handler 工具校验 — 实现

**Files:**
- Modify: `ai_end/src/core/todolist_handler.py`

**Step 1: 增加 REQUIRED_TOOLS 常量和校验逻辑**

在文件顶部新增常量，修改 `check_step` 签名和步骤 1/2 的 done 分支：

```python
"""
任务步骤检查点处理器 - 校验 todolist 各步骤完成情况
"""

# 各步骤 done 时必须调用的工具集合
REQUIRED_TOOLS: dict[int, set[str]] = {
    1: {"form_memory"},
    2: {"search_articles", "grep_article"},
}


async def check_step(step: int, status: str, called_tools: list[str], reason: str = "") -> dict:
    """
    任务步骤检查点。校验步骤完成情况，不合规则返回错误触发打回。

    Args:
        step: 当前步骤编号 (1, 2, 3)
        status: 步骤状态 (done, skip, start)
        called_tools: 当轮已调用的工具名列表（由 handlers.py 注入）
        reason: 跳过步骤时的理由（status=skip 时必填），done 时可选（调试日志）

    Returns:
        success=True: 步骤通过，message 包含下一步指引
        success=False: 步骤被打回，error 包含打回原因
    """
    if step == 1:
        if status == "start":
            return {"success": True, "message": "步骤1开始。请判断是否需要保存记忆，然后调用相应工具。"}
        if status == "done":
            return _validate_done(step, called_tools, "form_memory", "保存记忆",
                                  "请继续步骤2：判断是否需要查询文章。", reason)
        if status == "skip" and not _is_valid_skip_reason(reason):
            return {
                "success": False,
                "error": f"步骤1跳过理由不合理：'{reason}'。请重新判断是否需要保存记忆。",
            }
        return {"success": True, "message": "步骤1完成。请继续步骤2：判断是否需要查询文章。"}

    if step == 2:
        if status == "start":
            return {"success": True, "message": "步骤2开始。请判断是否需要查询文章，然后调用相应工具。"}
        if status == "done":
            return _validate_done(step, called_tools, "search_articles/grep_article", "查询文章",
                                  "请继续步骤3：整理并总结回答。", reason)
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


def _validate_done(
    step: int, called_tools: list[str], tool_desc: str,
    action_desc: str, next_hint: str, reason: str = "",
) -> dict:
    """校验 done 状态时必需工具是否被调用。"""
    required = REQUIRED_TOOLS.get(step, set())
    called_set = set(called_tools)

    if not required.intersection(called_set):
        return {
            "success": False,
            "error": f"步骤{step}要求调用{tool_desc}工具，但未检测到调用记录。请先执行{action_desc}再标记完成。",
        }

    message = f"步骤{step}完成。"
    if reason:
        message += f"备注: {reason}。"
    message += next_hint
    return {"success": True, "message": message}


def _is_valid_skip_reason(reason: str) -> bool:
    """校验跳过理由是否充分：不能为空，不能是无意义的短文本（至少5字符）。"""
    if not reason or len(reason.strip()) < 5:
        return False
    return True
```

**Step 2: 运行测试确认通过**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: 全部 PASS

---

### Task 3: handlers.py 注入 called_tools — 失败测试

**Files:**
- Modify: `ai_end/tests/unit/test_todolist_handler.py`

**Step 1: 新增集成测试验证 called_tools 注入**

在 `TestTodolistCheckIntegration` 类中追加测试：

```python
    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_without_form_memory_in_same_batch_rejected(self, todolist_skill_system):
        """同一批 tool_calls 中 done 但无 form_memory 应被打回"""
        from src.chat.handlers import handle_tool_calls

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_4"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is False
        assert "form_memory" in data["error"]

    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_with_form_memory_in_same_batch_passes(self, todolist_skill_system):
        """同一批 tool_calls 中 form_memory + done 应通过"""
        from src.chat.handlers import handle_tool_calls

        mock_form_memory = Mock()
        mock_form_memory.function.name = "form_memory"
        mock_form_memory.function.arguments = '{"reason": "test"}'
        mock_form_memory.id = "call_fm_1"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_5"

        result = await handle_tool_calls(
            [mock_form_memory, mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is True  # form_memory 的结果

        done_data = json.loads(result[1]["content"])
        assert done_data["success"] is True
        assert "步骤2" in done_data["message"]
```

**Step 2: 修改现有集成测试传入 called_tools 上下文**

`test_todolist_check_step1_done_through_handle_tool_calls` 需要在同一批 tool_calls 中包含 `form_memory` 才能通过新校验。更新为：

```python
    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_through_handle_tool_calls(self, todolist_skill_system):
        """todolist_check(step=1, status=done) 在同一批有 form_memory 时应通过"""
        from src.chat.handlers import handle_tool_calls

        mock_form_memory = Mock()
        mock_form_memory.function.name = "form_memory"
        mock_form_memory.function.arguments = '{"reason": "test"}'
        mock_form_memory.id = "call_fm_0"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_1"

        result = await handle_tool_calls(
            [mock_form_memory, mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        done_data = json.loads(result[1]["content"])
        assert done_data["success"] is True
        assert "步骤2" in done_data["message"]
```

**Step 3: 运行测试确认失败**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py::TestTodolistCheckIntegration -v`
Expected: FAIL（called_tools 未注入，校验失败）

---

### Task 4: handlers.py 注入 called_tools — 实现

**Files:**
- Modify: `ai_end/src/chat/handlers.py`

**Step 1: 在 handle_tool_calls 中收集 processed_tools 并注入**

在 `handle_tool_calls` 函数的 for 循环前初始化 `processed_tools`，在循环内每次处理后追加工具名，在分发二级工具时注入：

将 `handle_tool_calls` 中 for 循环部分修改为：

```python
    activated = activated_skills or set()
    tool_messages = []
    processed_tools: list[str] = []

    for tool_call in tool_calls:
        function_name = tool_call.function.name
        function_args_str = tool_call.function.arguments

        # 解析函数参数（如果有）
        try:
            function_args = json.loads(function_args_str) if function_args_str else {}
        except json.JSONDecodeError:
            function_args = {}

        # 处理不同类型的工具调用
        if function_name == "read_reference":
            # ... 保持不变 ...
        elif function_name == "form_memory":
            # ... 保持不变 ...
        else:
            skill_name = function_name.replace("call_skill_", "") if function_name.startswith("call_skill_") else function_name

            if skill_name in skill_system.available_skills:
                content = skill_system.get_skill_content(skill_name)
            else:
                # todolist_check 注入 called_tools
                if function_name == "todolist_check":
                    function_args["called_tools"] = list(processed_tools)
                content = await _handle_secondary_tool_call(function_name, function_args, skill_system, activated)
                # ... 后续 truncate 逻辑保持不变 ...

        # 记录已处理的工具名
        processed_tools.append(function_name)

        # 构建工具响应消息
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": content
        }
        tool_messages.append(tool_message)
```

注意：`processed_tools.append(function_name)` 放在 for 循环末尾（构建 tool_message 之前），确保 `todolist_check` 看到的是**它之前**已处理的工具列表。

**Step 2: 运行测试确认通过**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: 全部 PASS

---

### Task 5: SKILL.md 和 TOOLS.md 更新

**Files:**
- Modify: `ai_end/skills/todolist/SKILL.md`
- Modify: `ai_end/skills/todolist/TOOLS.md`

**Step 1: 更新 SKILL.md 引入 start 流程**

将 `skills/todolist/SKILL.md` 内容替换为：

```markdown
---
name: todolist
description: 任务执行检查点框架。每次对话必须先调用此技能，按步骤完成：1.判断保存记忆 2.判断查询文章 3.总结回答。不可跳过步骤。
verification_token: TODOLIST-FRAMEWORK-2026
---

# 任务执行框架

你必须按以下步骤顺序完成每次对话任务。**严格按顺序执行，不可跳过任何步骤。**

## 步骤 1：判断是否需要保存记忆

- **先调用 `todolist_check`，传入 `step=1, status=start` 标记开始**
- 如果用户分享了个人信息、偏好、知识或表达了明确的意图 → 调用 `form_memory` 工具执行记忆保存，然后调用 `todolist_check`，传入 `step=1, status=done`（可选传入 reason 记录原因）
- 如果用户只是在闲聊、打招呼、或没有提供有价值的信息 → 调用 `todolist_check`，传入 `step=1, status=skip, reason="..."`，**reason 必须充分具体**（至少5个字符），skip 即代表该步骤完成
- **注意**：标记 done 时系统会校验你是否真正调用了 form_memory，未调用将被打回
- **不得直接跳过此步骤，必须给出判断（执行或 skip 都算完成）**

## 步骤 2：判断是否需要查询文章

- **先调用 `todolist_check`，传入 `step=2, status=start` 标记开始**
- 如果用户问题与 OA 文章/通知/公告相关 → 调用 `article-retrieval` 技能，然后使用 `search_articles` / `grep_article` 查询，完成后调用 `todolist_check`，传入 `step=2, status=done`
- 如果用户问题与 OA 文章无关 → 调用 `todolist_check`，传入 `step=2, status=skip, reason="..."`，**reason 必须充分具体**
- **注意**：标记 done 时系统会校验你是否真正调用了搜索工具（search_articles/grep_article），未调用将被打回
- **不得直接跳过此步骤，必须给出判断（执行或 skip 都算完成）**

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

**Step 2: 更新 TOOLS.md 增加 called_tools 参数**

将 `skills/todolist/TOOLS.md` 内容替换为：

```yaml
tools:
  - name: todolist_check
    description: |
      任务步骤检查点。每完成一个步骤后必须调用此工具报告进度。
      如果跳过步骤，必须提供合理理由（至少5个字符），否则将被打回。
      标记 done 时，系统会校验当轮是否调用了该步骤的必需工具，未调用将被打回。
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
          description: status=skip 时必填（至少5个字符），status=done 时可选（用于调试日志）
        called_tools:
          type: array
          items:
            type: string
          description: "系统自动注入，当轮已调用的工具名列表。LLM 无需手动填写。"
      required: [step, status]
    handler: todolist_handler.check_step
```

**Step 3: 验证 YAML 格式**

Run: `cd ai_end && python -c "import yaml; data = yaml.safe_load(open('skills/todolist/TOOLS.md')); print(data['tools'][0]['name'])"`
Expected: `todolist_check`

---

### Task 6: 全量回归测试

**Step 1: 运行全部 todolist 测试**

Run: `cd ai_end && uv run pytest tests/unit/test_todolist_handler.py -v`
Expected: 全部 PASS

**Step 2: 运行全部单元测试确认无回归**

Run: `cd ai_end && uv run pytest tests/unit/ -v`
Expected: 全部 PASS，无新增失败
