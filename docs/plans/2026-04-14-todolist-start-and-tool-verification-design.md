# Todolist Start 标签 + 工具调用校验设计

## 背景

当前 todolist 框架的步骤流程是 **执行工具 → 调用 `todolist_check(status=done)`**，但 LLM 可能未真正调用指定工具就直接报 done（"撒谎"行为）。

本次增强引入 `start` 标签和 done 时的工具调用校验，确保 LLM 真正执行了步骤要求的操作。

## 需求

1. **start 标签**：步骤开始时调用 `todolist_check(step=N, status=start)`，作为 LLM 的"自提醒"占位
2. **done 校验**：调用 `todolist_check(step=N, status=done)` 时，后端校验当轮是否调用了该步骤的必需工具
3. **reason 扩展**：`done` 状态也支持传入 `reason`，用于调试日志（不参与校验）
4. **无状态**：校验基于当轮 tool_calls 列表，不维护会话级状态

## 方案：Handler 注入上下文（方案 A）

### 核心思路

给 `check_step` 增加 `called_tools` 参数，在 `handlers.py` 调用 `todolist_check` 时将当轮已调用的工具名列表注入。

### 校验规则

| 步骤 | 必需工具 | done 校验 |
|------|----------|-----------|
| 1 | `form_memory` | `called_tools` 中包含 `form_memory` |
| 2 | `search_articles` 或 `grep_article` | `called_tools` 中包含任一 |
| 3 | 无 | 始终通过 |

### 无后门原则

`called_tools` 始终由 `handlers.py` 注入，`check_step` **不做 None 跳过**。缺少必需工具直接打回，不预留兼容出口。

## 改动清单

### 1. `src/core/todolist_handler.py`

- `check_step` 签名增加 `called_tools: list[str]`（必填，不设默认值）
- 新增常量 `REQUIRED_TOOLS = {1: {"form_memory"}, 2: {"search_articles", "grep_article"}}`
- 步骤 1/2 的 `status=done` 分支：校验 `called_tools` 是否包含必需工具
- 步骤 1/2 的 `status=start` 分支：返回开始消息
- 步骤 1/2 的 `status=skip` 分支：保持现有理由校验
- `done` 通过时在 message 中附带 reason（如有）

### 2. `src/chat/handlers.py`

- 在 `handle_tool_calls` 的 for 循环中维护 `processed_tools: list[str]`
- 遇到 `todolist_check` 调用时，将 `called_tools` 注入 `function_args`

### 3. `skills/todolist/SKILL.md`

- 步骤 1：增加 `start` → `form_memory`/skip → `done` 流程
- 步骤 2：增加 `start` → `article-retrieval`/skip → `done` 流程

### 4. `skills/todolist/TOOLS.md`

- `called_tools` 参数：`type: array, items: string`，系统自动注入，LLM 无需填写
- `reason` description 更新：`status=skip` 时必填（>=5字符），`status=done` 时可选（调试日志）

### 5. `tests/unit/test_todolist_handler.py`

新增用例：
- 步骤 1 done + 无 form_memory → 打回
- 步骤 1 done + 有 form_memory → 通过
- 步骤 1 done + 有 reason → message 附带 reason
- 步骤 2 done + 无搜索工具 → 打回
- 步骤 2 done + 有 search_articles → 通过
- 步骤 2 done + 有 grep_article → 通过
- 各步骤 start → 返回开始消息
- called_tools 为空列表 → 打回（等同于未调用必需工具）

## 数据流

```
LLM 同一轮返回多个 tool_calls:
  [todolist_check(step=1, status=start), form_memory(...), todolist_check(step=1, status=done)]

handle_tool_calls 处理:
  1. todolist_check(start) → processed_tools=[], 调用 check_step(step=1, status="start") → 返回开始消息
  2. form_memory → processed_tools=["form_memory"], 正常处理
  3. todolist_check(done) → processed_tools=["form_memory","todolist_check"], 注入 called_tools=["form_memory","todolist_check"]
     → check_step(step=1, status="done", called_tools=["form_memory","todolist_check"]) → 校验通过
```

## 技术债评估

- **低**：无状态设计，参数显式传递，校验逻辑集中在 handler，可测试性好
- **无后门**：`called_tools` 始终注入，校验不可绕过
