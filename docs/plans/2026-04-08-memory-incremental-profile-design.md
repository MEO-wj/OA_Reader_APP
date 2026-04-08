# 记忆系统 v2 增量画像与测试修复设计

- 日期: 2026-04-08
- 状态: 评审通过
- 基线文档: docs/plans/2026-04-08-memory-unified-v2-retry-design.md
- 范围: 已有画像注入 prompt、测试修复、设计文档勘误

## 1. 目标

1. 记忆生成 prompt 注入数据库已有用户画像，让 LLM 增量完善而非从零生成。
2. 新旧信息冲突时以当前对话为准。
3. 修复代码审查发现的问题（I3、S3）。
4. 勘误设计文档（I1、S2，已完成）。

## 2. 核心约束

1. 注入前必须校验已有画像为 v2 格式，v1 或非法 JSON 视为无画像。
2. 复用已有 `_validate_v2_memory_schema` 做校验，零新增校验逻辑。
3. 仅首次 prompt 注入已有画像，重试 prompt 不注入。
4. 不改数据库结构、不改 LLM 输出格式、不改 `_parse_memory` 解析逻辑。

## 3. 方案：扩展 MEMORY_PROMPT_TEMPLATE

### 3.1 提示词模板变更

MEMORY_PROMPT_TEMPLATE 末尾新增可选段落：

```
## 已有用户画像（仅供参考，请基于当前对话更新，冲突以当前对话为准）
{existing_profile}
```

- `{existing_profile}` 为空字符串时，整段不显示。
- 明确指引 LLM 增量更新策略。

### 3.2 数据流

```
form_memory(messages)
  ├── _load_existing_profile()    # 新增：从 DB 加载已有画像
  │     ├── DB.get_profile(user_id)
  │     ├── json.loads(portrait_text)
  │     ├── _validate_v2_memory_schema()  # 复用已有校验
  │     └── 通过 → 格式化为可读文本 / 失败 → 返回空字符串
  ├── _build_memory_prompt(messages, existing_profile)  # 修改：传入已有画像
  │     └── MEMORY_PROMPT_TEMPLATE.format(conversation=..., existing_profile=...)
  └── LLM → _parse_memory → 保存
```

### 3.3 `_load_existing_profile` 实现

```python
async def _load_existing_profile(self) -> str:
    """从 DB 加载已有用户画像，校验 v2 格式后返回可读文本。

    v1 或非法 JSON 返回空字符串（等效于无画像）。
    """
    profile = await self.memory_db.get_profile(self.user_id)
    if not profile:
        return ""

    portrait_raw = profile.get("portrait_text", "") or ""
    knowledge_raw = profile.get("knowledge_text", "") or ""

    if not portrait_raw:
        return ""

    # 校验 portrait 为 v2 格式
    try:
        portrait_data = json.loads(portrait_raw)
    except (json.JSONDecodeError, TypeError):
        return ""

    if not isinstance(portrait_data, dict):
        return ""

    if not self._validate_v2_memory_schema(portrait_data):
        return ""  # v1 或结构不对

    # 格式化为可读文本
    sections = []
    confirmed = portrait_data.get("confirmed", {})
    if confirmed.get("identity"):
        sections.append("已确认身份: " + ", ".join(confirmed["identity"]))
    if confirmed.get("interests"):
        sections.append("已确认兴趣: " + ", ".join(confirmed["interests"]))
    if confirmed.get("constraints"):
        sections.append("已确认约束: " + ", ".join(confirmed["constraints"]))

    hypothesized = portrait_data.get("hypothesized", {})
    if hypothesized.get("identity"):
        sections.append("推测身份: " + ", ".join(hypothesized["identity"]))
    if hypothesized.get("interests"):
        sections.append("推测兴趣: " + ", ".join(hypothesized["interests"]))

    # knowledge 校验（宽松：合法 JSON 即可）
    if knowledge_raw:
        try:
            knowledge_data = json.loads(knowledge_raw)
            if isinstance(knowledge_data, dict):
                if knowledge_data.get("confirmed_facts"):
                    sections.append("已确认事实: " + ", ".join(knowledge_data["confirmed_facts"]))
                if knowledge_data.get("pending_queries"):
                    sections.append("待查询事项: " + ", ".join(knowledge_data["pending_queries"]))
        except (json.JSONDecodeError, TypeError):
            pass

    return "\n".join(sections) if sections else ""
```

### 3.4 `_build_memory_prompt` 变更

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

### 3.5 `_build_retry_prompt` 不变

重试 prompt 保持原有逻辑：仅 messages + last_error，不注入已有画像。

### 3.6 `form_memory` 签名变更

`_build_memory_prompt` 变为 `async` 方法，`form_memory` 中 `await` 调用即可。

## 4. 复用分析

| 复用目标 | 来源 | 复用方式 |
|---------|------|---------|
| `_validate_v2_memory_schema` | MemoryManager classmethod | 直接调用 `self._validate_v2_memory_schema()` |
| `get_profile` | MemoryDB | 直接调用 `self.memory_db.get_profile()` |

不引入新校验逻辑，不引入新依赖。

## 5. 测试修复

### 5.1 I3 - 重试 prompt 断言修正

文件: `tests/unit/test_memory_manager.py:564`

将无效断言替换为验证重试 prompt 结构特征：

```python
assert "你好" in retry_prompt
assert "第1次尝试" in retry_prompt
assert "请严格按要求输出合法 JSON" in retry_prompt
```

### 5.2 S3 - 集成测试 mock 数据修正

文件: `tests/integration/test_profile_integration.py:96`

将 mock JSON 中的 `confirmed_facts`/`pending_queries` 移入 `knowledge` 包装：

```python
'{"confirmed":{...},"hypothesized":{...},"knowledge":{"confirmed_facts":[],"pending_queries":["分数线"]}}'
```

### 5.3 新功能测试

1. 有 v2 画像时 prompt 包含已有画像段落。
2. 无画像时 prompt 不包含已有画像段落。
3. v1 画像时等同无画像（不注入）。
4. 非法 JSON 画像时等同无画像。
5. 重试 prompt 不包含已有画像段落。

## 6. 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `docs/plans/2026-04-08-memory-unified-v2-retry-design.md` | 勘误 | I1 + S2 已完成 |
| `src/chat/prompts_runtime.py` | 修改 | MEMORY_PROMPT_TEMPLATE 增加 `{existing_profile}` 占位符 |
| `src/chat/memory_manager.py` | 修改 | 新增 `_load_existing_profile`，`_build_memory_prompt` 改 async |
| `tests/unit/test_memory_manager.py` | 修改 | 修复 I3 断言 + 新增画像注入测试 |
| `tests/integration/test_profile_integration.py` | 修改 | 修复 S3 mock 数据 |
| `tests/unit/test_prompts_runtime.py` | 修改 | 验证模板包含 `{existing_profile}` |
