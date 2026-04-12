---
name: todolist
description: 任务执行检查点框架。每次对话必须先调用此技能，按步骤完成：1.判断保存记忆 2.判断查询文章 3.总结回答。不可跳过步骤。
verification_token: TODOLIST-FRAMEWORK-2026
---

# 任务执行框架

你必须按以下步骤顺序完成每次对话任务。**严格按顺序执行，不可跳过任何步骤。**

## 步骤 1：判断是否需要保存记忆

- 如果用户分享了个人信息、偏好、知识或表达了明确的意图 → 调用 `form_memory` 工具执行记忆保存，然后调用 `todolist_check`，传入 `step=1, status=done`
- 如果用户只是在闲聊、打招呼、或没有提供有价值的信息 → 调用 `todolist_check`，传入 `step=1, status=skip, reason="..."`，**reason 必须充分具体**（至少5个字符），skip 即代表该步骤完成
- **不得直接跳过此步骤，必须给出判断（执行或 skip 都算完成）**

## 步骤 2：判断是否需要查询文章

- 如果用户问题与 OA 文章/通知/公告相关 → 调用 `article-retrieval` 技能，然后使用 `search_articles` / `grep_article` 查询，完成后调用 `todolist_check`，传入 `step=2, status=done`
- 如果用户问题与 OA 文章无关 → 调用 `todolist_check`，传入 `step=2, status=skip, reason="..."`，**reason 必须充分具体**，skip 即代表该步骤完成
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
