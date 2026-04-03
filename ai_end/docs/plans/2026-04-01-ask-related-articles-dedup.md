# Ask Related Articles Dedup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 /ask 兼容接口 related_articles 重复问题，并对重复命中的 ebd_similarity、keyword_similarity、rerank_score 按各自非空样本平均值输出。

**Architecture:** 在 compat 聚合层新增“标准化 + 按 id 去重聚合”流程，不改动 /ask 响应结构和检索核心逻辑。事件遍历阶段仅收集 search_articles 结果，遍历结束后一次性执行聚合，确保跨多次 tool_result 的重复也被消除。采用 TDD：先为重复与平均值行为补失败测试，再做最小实现，通过单测和集成回归验证。

**Tech Stack:** Python 3.11, FastAPI, pytest, monkeypatch, asyncio

---

### Task 1: 为按 id 去重与均值聚合建立失败测试

**Files:**
- Modify: tests/unit/test_compat_service.py
- Test: tests/unit/test_compat_service.py

**Step 1: Write the failing test**

```python
def test_aggregate_events_dedup_by_id_and_average_scores():
    from src.api.compat_service import CompatService

    events = [
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": [
                {
                    "id": 101,
                    "title": "文章A",
                    "summary": "摘要A-1",
                    "ebd_similarity": 0.8,
                    "keyword_similarity": None,
                    "rerank_score": 0.7,
                }
            ],
        },
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": {
                "results": [
                    {
                        "id": 101,
                        "title": "文章A",
                        "summary": "摘要A-2",
                        "ebd_similarity": None,
                        "keyword_similarity": 0.9,
                        "rerank_score": 0.5,
                    },
                    {
                        "id": 101,
                        "title": "文章A",
                        "summary": "摘要A-3",
                        "ebd_similarity": 0.6,
                        "keyword_similarity": 0.3,
                        "rerank_score": None,
                    },
                ]
            },
        },
    ]

    result = CompatService._aggregate_events(events)
    assert len(result["related_articles"]) == 1
    doc = result["related_articles"][0]
    assert doc["id"] == 101
    assert doc["ebd_similarity"] == pytest.approx(0.7)
    assert doc["keyword_similarity"] == pytest.approx(0.6)
    assert doc["rerank_score"] == pytest.approx(0.6)
```

**Step 2: Run test to verify it fails**

Run: pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_aggregate_events_dedup_by_id_and_average_scores -v
Expected: FAIL，因当前逻辑会重复追加，不会聚合平均值。

**Step 3: Write minimal implementation placeholder**

```python
# 在 CompatService._aggregate_events 中临时引入 all_docs 收集点
# 先不完整实现聚合，确保测试从“重复追加”失败进入“字段缺失/断言失败”状态，便于小步推进。
```

**Step 4: Run test to verify controlled failure**

Run: pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_aggregate_events_dedup_by_id_and_average_scores -v
Expected: 仍 FAIL，但失败点应收敛到具体聚合逻辑断言。

### Task 2: 实现标准化与去重聚合核心逻辑

**Files:**
- Modify: src/api/compat_service.py
- Test: tests/unit/test_compat_service.py

**Step 1: Write the failing test for helper behavior**

```python
def test_aggregate_events_keeps_no_id_docs_passthrough():
    from src.api.compat_service import CompatService

    events = [
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": [
                {"id": 1, "title": "有ID", "ebd_similarity": 0.8},
                {"title": "无ID", "ebd_similarity": 0.9},
            ],
        },
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": [{"id": 1, "title": "有ID", "ebd_similarity": 0.6}],
        },
    ]

    result = CompatService._aggregate_events(events)
    assert len(result["related_articles"]) == 2
    assert sum(1 for x in result["related_articles"] if x.get("id") == 1) == 1
    assert any(x.get("id") is None for x in result["related_articles"])
```

**Step 2: Run test to verify it fails**

Run: pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_aggregate_events_keeps_no_id_docs_passthrough -v
Expected: FAIL。

**Step 3: Write minimal implementation**

```python
# src/api/compat_service.py
# 1) 新增 _normalize_tool_result_to_docs(parsed)
# 2) 新增 _dedupe_and_aggregate_docs(docs)
#    - 有 id: 按 id 聚合
#    - 无 id: passthrough
#    - 三个评分字段分别 sum/count
# 3) _aggregate_events 中将 related_articles.extend(...) 改为:
#    - all_docs.extend(normalized_docs)
#    - 循环结束后 related_articles = _dedupe_and_aggregate_docs(all_docs)
```

**Step 4: Run targeted tests to verify pass**

Run: pytest tests/unit/test_compat_service.py::TestAggregateEvents -v
Expected: PASS（新老聚合测试均通过）。

### Task 3: 补强异常与数据兼容测试

**Files:**
- Modify: tests/unit/test_compat_service.py
- Modify: src/api/compat_service.py
- Test: tests/unit/test_compat_service.py

**Step 1: Write failing tests for invalid score inputs**

```python
def test_aggregate_events_ignores_invalid_score_values():
    from src.api.compat_service import CompatService

    events = [
        {
            "type": "tool_result",
            "tool": "search_articles",
            "result": [
                {"id": 7, "title": "A", "ebd_similarity": "bad", "keyword_similarity": True, "rerank_score": float("nan")},
                {"id": 7, "title": "A", "ebd_similarity": 0.5, "keyword_similarity": None, "rerank_score": 0.4},
            ],
        }
    ]

    result = CompatService._aggregate_events(events)
    doc = result["related_articles"][0]
    assert doc["ebd_similarity"] == pytest.approx(0.5)
    assert doc["keyword_similarity"] is None
    assert doc["rerank_score"] == pytest.approx(0.4)
```

**Step 2: Run test to verify it fails**

Run: pytest tests/unit/test_compat_service.py::TestAggregateEvents::test_aggregate_events_ignores_invalid_score_values -v
Expected: FAIL。

**Step 3: Write minimal implementation**

```python
# 新增数值校验辅助逻辑:
# - 仅接受 int/float 且非 bool 且非 NaN
# - 非法值不计入 sum/count
```

**Step 4: Run unit tests for compat service**

Run: pytest tests/unit/test_compat_service.py -q
Expected: PASS。

### Task 4: 集成回归验证与文档同步

**Files:**
- Test: tests/integration/test_compat_endpoints.py
- Modify: docs/plans/2026-04-01-ask-related-articles-dedup-design.md

**Step 1: Verify existing integration tests still describe contract**

```python
# 如无需改断言，仅确认 /ask 仍返回 answer 与 related_articles
# 不新增契约破坏性字段
```

**Step 2: Run integration regression**

Run: pytest tests/integration/test_compat_endpoints.py -q
Expected: PASS。

**Step 3: Update design doc with implementation notes (if needed)**

```markdown
- 补充“最终实现点位”和“新增测试名称”
- 记录平均值规则: 仅统计非空有效数值
```

**Step 4: Run focused full check**

Run: pytest tests/unit/test_compat_service.py tests/integration/test_compat_endpoints.py -q
Expected: PASS。

