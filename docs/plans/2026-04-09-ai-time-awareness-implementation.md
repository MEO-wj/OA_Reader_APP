# AI Time Awareness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 AI 端具备时间感知与按日期范围检索能力，支持纯时间查询并在排序中引入温和时效性加权。

**Architecture:** 采用三层改造：聊天层注入当前日期，工具层扩展日期参数契约，检索层统一应用日期过滤与时效性打分。保持与现有调用链兼容，不引入服务端自然语言时间解析模块。

**Tech Stack:** Python 3.11, pytest, asyncpg/PostgreSQL, OpenAI-compatible SDK, OA ai_end 现有检索模块

---

### Task 1: 系统提示词模板支持日期占位符

**Files:**
- Modify: `ai_end/src/chat/prompts_runtime.py`
- Test: `ai_end/tests/unit/test_memory_chat.py`

**Step 1: Write the failing test**

在 `ai_end/tests/unit/test_memory_chat.py` 新增一个最小测试，断言系统提示词模板包含 `当前日期：{current_date}（{weekday}）`。

```python
def test_system_prompt_template_contains_date_placeholders():
    from src.chat.prompts_runtime import SYSTEM_PROMPT_TEMPLATE

    assert "当前日期：{current_date}（{weekday}）" in SYSTEM_PROMPT_TEMPLATE
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py::test_system_prompt_template_contains_date_placeholders -v`
Expected: FAIL（模板尚未包含占位符）

**Step 3: Write minimal implementation**

在 `SYSTEM_PROMPT_TEMPLATE` 顶部加一行占位文本：

```python
SYSTEM_PROMPT_TEMPLATE = """你是一个通用 AI Agent 助手。
当前日期：{current_date}（{weekday}）
...
"""
```

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py::test_system_prompt_template_contains_date_placeholders -v`
Expected: PASS


### Task 2: ChatClient 注入当前日期与星期（AI_COMPAT_TZ）

**Files:**
- Modify: `ai_end/src/chat/client.py`
- Test: `ai_end/tests/unit/test_memory_chat.py`

**Step 1: Write the failing test**

新增测试，mock 配置时区与当前时间，断言 `_build_system_prompt()` 输出包含正确日期与星期。

```python
@pytest.mark.asyncio
async def test_build_system_prompt_injects_current_date_and_weekday(monkeypatch):
    from src.chat.client import ChatClient

    # 构造最小 client（可通过 monkeypatch skill_system / config）
    ...
    prompt = client._build_system_prompt()

    assert "当前日期：2026-04-09（星期四）" in prompt
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py::test_build_system_prompt_injects_current_date_and_weekday -v`
Expected: FAIL

**Step 3: Write minimal implementation**

在 `ai_end/src/chat/client.py` 的 `_build_system_prompt()` 增加：

1. 读取 `self.config.compat_timezone`
2. 使用 `zoneinfo.ZoneInfo`（或安全回退）获取当前时间
3. 生成 `current_date` 与中文星期映射
4. 在 `self.DEFAULT_SYSTEM_PROMPT.format(...)` 注入 `current_date`、`weekday`

```python
weekday_map = {0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 4: "星期五", 5: "星期六", 6: "星期日"}
```

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_memory_chat.py::test_build_system_prompt_injects_current_date_and_weekday -v`
Expected: PASS


### Task 3: 扩展 search_articles 工具参数契约

**Files:**
- Modify: `ai_end/skills/article-retrieval/TOOLS.md`
- Test: `ai_end/tests/unit/test_tools_contract.py` (create)

**Step 1: Write the failing test**

创建 `ai_end/tests/unit/test_tools_contract.py`，读取 TOOLS.md 并断言：

1. `search_articles` 的 `query` 非 required
2. 存在 `start_date`、`end_date`
3. 描述包含 `YYYY-MM-DD`

```python
def test_search_articles_contract_supports_date_range():
    text = Path("ai_end/skills/article-retrieval/TOOLS.md").read_text(encoding="utf-8")
    assert "start_date" in text
    assert "end_date" in text
    assert "YYYY-MM-DD" in text
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_tools_contract.py::test_search_articles_contract_supports_date_range -v`
Expected: FAIL

**Step 3: Write minimal implementation**

更新 TOOLS.md：

1. `query` 从 required 移除
2. 新增 `start_date` / `end_date` 参数说明
3. 为空 query 场景补充说明

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_tools_contract.py::test_search_articles_contract_supports_date_range -v`
Expected: PASS


### Task 4: 检索层日期过滤（有 query 分支）

**Files:**
- Modify: `ai_end/src/core/article_retrieval.py`
- Test: `ai_end/tests/unit/test_article_retrieval.py`

**Step 1: Write the failing test**

在 `test_article_retrieval.py` 新增：传入 `query + start_date + end_date` 时，SQL 包含 `published_on` 下上界条件。

```python
@pytest.mark.asyncio
async def test_search_articles_adds_date_range_filter_to_sql(...):
    ...
    await search_articles("奖学金", start_date="2026-04-01", end_date="2026-04-09")
    assert "published_on" in captured_sql
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_search_articles_adds_date_range_filter_to_sql -v`
Expected: FAIL

**Step 3: Write minimal implementation**

在 `ai_end/src/core/article_retrieval.py` 中：

1. 扩展 `search_articles(...)` 签名加入 `start_date`, `end_date`
2. 增加日期解析函数（仅格式校验，不做时间词解析）
3. 扩展 `_vector_search(...)` 与 `_search_by_keywords(...)` 入参并拼接日期过滤 SQL

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_search_articles_adds_date_range_filter_to_sql -v`
Expected: PASS


### Task 5: 纯时间查询分支（query 可空）

**Files:**
- Modify: `ai_end/src/core/article_retrieval.py`
- Test: `ai_end/tests/unit/test_article_retrieval.py`

**Step 1: Write the failing test**

新增测试：`query` 为空时不调用 embedding，直接按 `published_on DESC` 返回。

```python
@pytest.mark.asyncio
async def test_search_articles_empty_query_returns_latest_by_date(...):
    ...
    result = await search_articles(query="", top_k=3)
    assert [x["id"] for x in result["results"]] == [3, 2, 1]
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_search_articles_empty_query_returns_latest_by_date -v`
Expected: FAIL（当前实现抛出“查询文本不能为空”）

**Step 3: Write minimal implementation**

在 `search_articles` 中：

1. 删除空 query 的异常抛出
2. 新增纯时间查询 SQL 分支
3. 支持与合法日期过滤叠加

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_search_articles_empty_query_returns_latest_by_date -v`
Expected: PASS

### Task 6: 时效性加权排序

**Files:**
- Modify: `ai_end/src/core/article_retrieval.py`
- Test: `ai_end/tests/unit/test_article_retrieval.py`

**Step 1: Write the failing test**

新增测试：同 `similarity` 条件下，发布时间更新的文档 `final_score` 更高。

```python
@pytest.mark.asyncio
async def test_recency_weight_prefers_newer_article_when_similarity_equal(...):
    ...
    assert newer["final_score"] > older["final_score"]
```

**Step 2: Run test to verify it fails**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_recency_weight_prefers_newer_article_when_similarity_equal -v`
Expected: FAIL

**Step 3: Write minimal implementation**

在 SQL 或 Python 合并排序逻辑中引入：

```python
final_score = similarity - 0.1 * exp(-days_old / 30)
```

并确保返回结构中的排序依据一致。

**Step 4: Run test to verify it passes**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_recency_weight_prefers_newer_article_when_similarity_equal -v`
Expected: PASS


### Task 7: 日期边界与容错行为

**Files:**
- Modify: `ai_end/src/core/article_retrieval.py`
- Test: `ai_end/tests/unit/test_article_retrieval.py`

**Step 1: Write the failing tests**

一次新增三个测试：

1. `start_date > end_date` 自动交换
2. 非法日期格式忽略并降级
3. 单边界场景（仅 start 或仅 end）符合设计

```python
@pytest.mark.asyncio
async def test_date_range_swapped_when_start_after_end(...): ...

@pytest.mark.asyncio
async def test_invalid_date_is_ignored(...): ...

@pytest.mark.asyncio
async def test_single_boundary_behaviors(...): ...
```

**Step 2: Run test to verify they fail**

Run:
- `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_date_range_swapped_when_start_after_end -v`
- `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_invalid_date_is_ignored -v`
- `cd ai_end; pytest tests/unit/test_article_retrieval.py::test_single_boundary_behaviors -v`

Expected: FAIL

**Step 3: Write minimal implementation**

新增日期规范化函数（示例 `_normalize_date_range`）：

1. 尝试解析 `%Y-%m-%d`
2. 非法值置 `None`
3. 双边界且反转时交换
4. 仅 `start_date` 时 `end_date=today(tz)`

**Step 4: Run tests to verify they pass**

Run: `cd ai_end; pytest tests/unit/test_article_retrieval.py -k "date_range_swapped or invalid_date_is_ignored or single_boundary_behaviors" -v`
Expected: PASS


### Task 8: 回归验证与文档同步

**Files:**
- Modify: `ai_end/skills/article-retrieval/TOOLS.md` (若前面未补齐说明)
- Test: `ai_end/tests/unit/test_article_retrieval.py`, `ai_end/tests/unit/test_memory_chat.py`, `ai_end/tests/unit/test_tools_contract.py`

**Step 1: Run focused regression tests**

Run:
- `cd ai_end; pytest tests/unit/test_memory_chat.py -v`
- `cd ai_end; pytest tests/unit/test_tools_contract.py -v`
- `cd ai_end; pytest tests/unit/test_article_retrieval.py -v`

Expected: 全部 PASS

**Step 2: Run broader safety test set**

Run: `cd ai_end; pytest tests/unit -v`
Expected: PASS（若有历史已知失败，记录并隔离）

**Step 3: PR checklist**

1. 确认不包含服务端自然语言时间解析逻辑
2. 确认 `AI_COMPAT_TZ` 生效并有回退策略
3. 确认空 query 行为已从报错改为时间排序
4. 确认新增参数不破坏旧调用
