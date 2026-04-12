# TodoList 强制执行框架设计

## 概述

新增 `todolist` 技能，作为 LLM 每次对话的强制执行框架。要求 LLM 按步骤完成任务（判断记忆 → 判断文章 → 总结回答），未完成步骤时通过工具返回错误信息打回。

## 需求

| 维度 | 决定 |
|------|------|
| 角色定位 | 强制框架 — LLM 每次对话自动调用 |
| 打回机制 | 工具返回错误信息，强制 LLM 重新执行 |
| 步骤1 记忆 | 复用现有 `form_memory` 工具 |
| 步骤2 文章 | 查询已有文章（复用 `article-retrieval` 技能） |
| 执行方式 | 无状态检查点 — LLM 同次回复中依次执行各步骤 |

## 方案选择

选择 **方案 B：技能 + Handler 增强**。

- 比纯技能文件方案多了真正的硬打回能力（不是纯靠 prompt）
- 比聊天循环拦截方案侵入性小得多，不碰核心聊天循环
- Handler 增强是现有 `_dispatch_secondary_tool` 模式的自然延伸
- 技术债可控

## 数据流

```
用户消息 → ChatClient.chat_stream_async()
  ├── 构建 tools 列表（todolist 作为一级工具始终存在）
  ├── LLM 第1轮：调用 todolist（step=1）
  │     → todolist_handler.py 处理 → 返回"请先判断是否保存记忆"
  ├── LLM 第2轮：调用 form_memory（status=skip, reason="用户只是问候"）
  │     → handlers.py 处理 → 返回"记忆已跳过"
  │     → 同时调用 todolist_check（step=1, status=done）
  │     → handler 校验 → 返回"步骤1完成，请继续步骤2"
  ├── LLM 第3轮：判断无需查询文章
  │     → 调用 todolist_check（step=2, status=skip, reason="无需查询文章"）
  │     → handler 校验理由合理 → 返回"步骤2已跳过，请继续步骤3"
  ├── LLM 第4轮：直接输出最终回答（步骤3）
  └── 回合结束
```

## 新增文件

### 1. `ai_end/skills/todolist/SKILL.md`

技能入口定义，YAML front matter + Markdown 正文。

```yaml
---
name: todolist
description: 任务执行检查点框架。每次对话必须先调用此技能，按步骤完成：1.判断保存记忆 2.判断查询文章 3.总结回答。不可跳过步骤。
verification_token: TODOLIST-FRAMEWORK-2026
---
```

正文描述三个步骤的执行规则和跳过条件。

### 2. `ai_end/skills/todolist/TOOLS.md`

二级工具 `todolist_check` 的定义。

```yaml
tools:
  - name: todolist_check
    description: |
      任务步骤检查点。每完成一个步骤后必须调用此工具报告进度。
      如果跳过步骤，必须提供合理理由，否则将被打回。
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
          description: 跳过步骤时的理由（status=skip 时必填）
      required: [step, status]
    handler: todolist_handler.check_step
```

### 3. `ai_end/src/core/todolist_handler.py`

```python
async def check_step(step: int, status: str, reason: str = "") -> dict:
    """
    任务步骤检查点。校验步骤完成情况，不合规则返回错误触发打回。

    返回:
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


def _is_valid_skip_reason(reason: str) -> bool:
    """校验跳过理由是否充分：不能为空，不能是无意义的短文本。"""
    if not reason or len(reason.strip()) < 5:
        return False
    return True
```

## 修改文件

### `ai_end/src/chat/handlers.py`

在 `_dispatch_secondary_tool` 的模块映射中新增一行：

```python
"todolist_handler": "src.core.todolist_handler",
```

## 改动范围

| 文件 | 改动类型 | 改动量 |
|------|----------|--------|
| `ai_end/skills/todolist/SKILL.md` | 新增 | ~40 行 |
| `ai_end/skills/todolist/TOOLS.md` | 新增 | ~25 行 |
| `ai_end/src/core/todolist_handler.py` | 新增 | ~40 行 |
| `ai_end/src/chat/handlers.py` | 修改 | +1 行 |

## 集成方式

新增技能需插入 `skills` 数据库表（通过 `AUTO_IMPORT=true` 自动导入，或手动 SQL）。

## 不涉及的文件

- `client.py` — 聊天循环无需改动
- `db_skill_system.py` — 技能加载机制无需改动
- `chat_service.py` — SSE 事件无需改动
- `tool_activation.py` — todolist 不是指导性技能
