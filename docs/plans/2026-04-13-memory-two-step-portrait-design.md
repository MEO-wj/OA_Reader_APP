# 记忆保存模块：两步式画像生成与合并

## 背景

当前 `MemoryManager.form_memory()` 采用单步式流程：将对话内容 + 已有画像拼成一个 prompt，让 LLM 一次性完成提取和合并。这导致 prompt 职责过重，当旧画像数据较多时容易遗漏或误合。

## 目标

将画像生成拆为两步：先从对话中提取新画像，再与旧画像合并。支持首版画像快速路径（无旧画像时跳过合并步骤）。

## 设计方案：方案 C（双 Prompt + 首版快速路径）

### 调用流程

```
form_memory(messages)
  ├── _extract_portrait(messages) → new_portrait JSON  [Step 1]
  ├── _has_existing_profile() → bool                   [快速路径判断]
  ├── 无旧画像 → 直接存 new_portrait                   [快速路径]
  └── 有旧画像 → _merge_portraits(old, new) → merged   [Step 2]
                    └── 存 merged
```

### 新增 Prompt 模板（prompts_runtime.py）

#### PORTRAIT_EXTRACT_PROMPT

- **输入**：对话内容（不含旧画像）
- **输出**：v2 JSON（confirmed / hypothesized / knowledge）
- **规则**：仅基于对话内容提取，不做合并推断，不参考旧画像

#### PORTRAIT_MERGE_PROMPT

- **输入**：旧画像 JSON + 新画像 JSON
- **输出**：合并后的 v2 JSON
- **规则**：
  - 冲突时新信息优先
  - 去重（语义相同的条目只保留一条）
  - hypothesized 不升入 confirmed
  - 空字段保留旧值
  - 删除不再相关的事实/查询

### MemoryManager 方法变更

| 方法 | 变化 |
|------|------|
| `form_memory()` | 内部串联两步（调用方无感知） |
| `_extract_portrait()` | **新增**，Step1：从对话提取画像 |
| `_merge_portraits()` | **新增**，Step2：新旧画像合并 |
| `_build_extract_prompt()` | **新增**，构建 Step1 的 prompt |
| `_build_merge_prompt()` | **新增**，构建 Step2 的 prompt |
| `_build_memory_prompt()` | 不再被主流程使用（保留兼容） |
| `_build_retry_prompt()` | 拆为 extract retry + merge retry |
| `_parse_memory()` | **复用**，Step1 和 Step2 均使用 |
| `_adjudicate_identity()` | **复用** |
| `_validate_v2_memory_schema()` | **复用** |

### 不变的部分

- 数据库 schema（portrait_text + knowledge_text）
- MemoryDB.save_profile()
- ChatClient 调用 form_memory() 的方式
- compact_messages() 中的画像摘要

### 重试协议

- Step1 和 Step2 各自独立重试（最多 3 次）
- Step1 失败 → 整体失败（沿用现有降级逻辑）
- Step1 成功 + Step2 失败 → 降级直接使用 Step1 结果存库

### 测试策略

1. Step1 画像提取：无旧画像场景
2. Step2 画像合并：有旧画像 + 新画像冲突/非冲突场景
3. 快速路径：旧画像为空时跳过 Step2
4. 降级兼容：Step1 失败 / Step2 失败
5. 回归：现有 form_memory 相关测试全部通过

## 技术债评估

- **低**：复用现有校验逻辑（_parse_memory, _adjudicate_identity）
- 新增两个 prompt 模板，不改变数据结构
- 调用方无感知，现有测试仅需适配内部流程
