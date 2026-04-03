# 兼容端点审查修复 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复兼容端点代码审查发现的 5 个已确认问题（异常处理、类型验证、测试覆盖、日志、类型标注）。

**Architecture:** 最小侵入式修复——每个问题在原文件内就地修复，不引入新文件或新抽象。按 TDD 模式：先写失败测试 → 实现 → 验证通过。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest

---

### Task 1: M3 类型标注修正（最简单的修复，热身）

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py:38` — `tz: Any` → `tz: ZoneInfo | timezone`
- Modify: `ai_end_refactor/src/api/compat_service.py:14` — 移除 `from typing import Any` 中不再需要的 `Any`（如果已无其他使用）

**Step 1: 验证 `Any` 是否还有其他使用**

检查 `compat_service.py` 中是否还有其他地方使用 `Any`。如果有（如 `build_runtime_hints` 的 `top_k: Any`、`_aggregate_events` 的参数），保留 import。

**Step 2: 修改类型标注**

将 `compat_service.py:38` 的：
```python
tz: Any = ZoneInfo(tz_name)
```
改为：
```python
tz: ZoneInfo | timezone = ZoneInfo(tz_name)
```

**Step 3: 运行现有测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: ALL PASS

---

### Task 2: M2 tool_result 解析失败日志

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py:174-176` — 在 except 块中加 logger.warning

**Step 1: 写失败测试**

在 `ai_end_refactor/tests/unit/test_compat_service.py` 中添加测试，验证非 JSON 字符串触发 warning 日志：

```python
def test_aggregate_events_logs_warning_on_invalid_json(caplog):
    """M2: tool_result 包含非 JSON 字符串时应输出 warning 日志。"""
    events = [
        {"type": "tool_result", "result": "<<<not-json>>>"},
    ]
    with caplog.at_level(logging.WARNING, logger="src.api.compat_service"):
        result = CompatService._aggregate_events(events)

    assert result["related_articles"] == []
    assert any("Failed to parse tool_result" in rec.message for rec in caplog.records)
```

注意：在文件顶部确认 `import logging` 已存在。

**Step 2: 运行测试验证失败**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::test_aggregate_events_logs_warning_on_invalid_json -v`
Expected: FAIL — `assert any(...)` 失败，因为还没有 warning 日志

**Step 3: 实现——在 except 块中添加 logger.warning**

将 `compat_service.py:174-176` 的：
```python
                    try:
                        parsed = json.loads(raw_result)
                    except (json.JSONDecodeError, TypeError):
                        parsed = None
```
改为：
```python
                    try:
                        parsed = json.loads(raw_result)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "Failed to parse tool_result as JSON: %s",
                            raw_result[:200],
                        )
                        parsed = None
```

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::test_aggregate_events_logs_warning_on_invalid_json -v`
Expected: PASS

**Step 5: 运行全部 compat 测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: ALL PASS

---

### Task 3: I1 top_k 模型层验证（拒绝 bool）

**Files:**
- Modify: `ai_end_refactor/src/api/compat_models.py` — 添加 `field_validator`
- Test: `ai_end_refactor/tests/unit/test_compat_service.py`（已有 `test_top_k_bool_is_rejected`，需验证）

**Step 1: 确认现有测试覆盖**

检查 `test_compat_service.py` 中是否已有 `test_top_k_bool_is_rejected` 或类似测试。如果有，运行确认当前行为。

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -k "bool" -v`

**Step 2: 在 compat_models.py 添加 field_validator**

将 `compat_models.py` 的：
```python
"""旧 AI End 兼容请求模型"""

from pydantic import BaseModel


class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None
```
改为：
```python
"""旧 AI End 兼容请求模型"""

from pydantic import BaseModel, field_validator


class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None

    @field_validator("top_k", mode="before")
    @classmethod
    def _reject_bool_top_k(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError("top_k must be an integer or string, not boolean")
        return v
```

**Step 3: 添加验证测试**

在 `test_compat_service.py` 的 `TestBuildRuntimeHints` 类中（或适当位置）添加集成验证：

```python
def test_ask_compat_request_rejects_bool_top_k():
    """I1: AskCompatRequest 应在模型层拒绝 bool 类型的 top_k。"""
    from pydantic import ValidationError
    from src.api.compat_models import AskCompatRequest

    with pytest.raises(ValidationError, match="boolean"):
        AskCompatRequest(question="test", top_k=True)
```

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -k "bool" -v`
Expected: PASS

**Step 5: 运行全部 compat 测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py tests/unit/test_config_compat.py tests/unit/test_memory_compat.py tests/integration/test_compat_endpoints.py -v`
Expected: ALL PASS

---

### Task 4: I5 补充集成测试（成功路径）

**Files:**
- Modify: `ai_end_refactor/tests/integration/test_compat_endpoints.py` — 添加 2 个测试

**Step 1: 写 test_clear_memory_success 测试**

在 `test_compat_endpoints.py` 末尾添加：

```python
# ---------------------------------------------------------------------------
# 成功路径测试
# ---------------------------------------------------------------------------


async def _mock_clear_memory(self, user_id: str | None = None):
    """CompatService.clear_memory 的 mock 实现。"""
    return {"cleared": True, "conversation_id": "mock-session-id"}


def test_clear_memory_success(monkeypatch):
    """clear_memory 成功时返回 200 和 cleared + conversation_id。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "clear_memory", _mock_clear_memory)
    client = TestClient(app)

    resp = client.post("/clear_memory", json={"user_id": "user123"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["cleared"] is True
    assert "conversation_id" in data
```

**Step 2: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py::test_clear_memory_success -v`
Expected: PASS

**Step 3: 写 test_ask_with_user_id_success 测试**

```python
async def _mock_ask_with_session(self, **kwargs):
    """CompatService.ask 的 mock 实现，返回带会话信息的结果。"""
    return {
        "answer": "mock answer",
        "related_articles": [{"title": "test"}],
        "conversation_id": "mock-conv-id",
        "session_created": True,
    }


def test_ask_with_user_id_success(monkeypatch):
    """ask 携带 user_id 时返回 200 和会话字段。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "ask", _mock_ask_with_session)
    client = TestClient(app)

    resp = client.post("/ask", json={"question": "测试", "user_id": "user123"})

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "related_articles" in data
    assert data["conversation_id"] == "mock-conv-id"
    assert data["session_created"] is True
```

**Step 4: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py::test_ask_with_user_id_success -v`
Expected: PASS

**Step 5: 运行全部集成测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -v`
Expected: ALL PASS

---

### Task 5: C1 兼容端点异常处理（最重要的修复）

**Files:**
- Modify: `ai_end_refactor/src/api/main.py:1-10` — 添加 `import logging`
- Modify: `ai_end_refactor/src/api/main.py:237-275` — 三个端点添加 try-except
- Test: `ai_end_refactor/tests/integration/test_compat_endpoints.py` — 添加异常路径测试

**Step 1: 写失败测试——验证异常被正确捕获**

在 `test_compat_endpoints.py` 末尾添加：

```python
# ---------------------------------------------------------------------------
# 异常处理测试（C1）
# ---------------------------------------------------------------------------


async def _mock_ask_raise(self, **kwargs):
    """CompatService.ask mock: 模拟下游异常。"""
    raise RuntimeError("LLM service unavailable")


async def _mock_clear_memory_raise(self, user_id=None):
    """CompatService.clear_memory mock: 模拟数据库异常。"""
    raise ConnectionError("Database connection failed")


async def _mock_embed_raise(self, text: str):
    """CompatService.embed mock: 模拟 API 异常。"""
    raise TimeoutError("Embedding API timeout")


def test_ask_returns_500_on_exception(monkeypatch):
    """C1: /ask 下游异常时应返回 500 + {"error": "..."}。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "ask", _mock_ask_raise)
    client = TestClient(app)

    resp = client.post("/ask", json={"question": "test"})

    assert resp.status_code == 500
    assert "error" in resp.json()


def test_clear_memory_returns_500_on_exception(monkeypatch):
    """C1: /clear_memory 下游异常时应返回 500 + {"error": "..."}。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "clear_memory", _mock_clear_memory_raise)
    client = TestClient(app)

    resp = client.post("/clear_memory", json={"user_id": "user123"})

    assert resp.status_code == 500
    assert "error" in resp.json()


def test_embed_returns_500_on_exception(monkeypatch):
    """C1: /embed 下游异常时应返回 500 + {"error": "..."}。"""
    from src.api.main import app
    from src.api.compat_service import CompatService

    monkeypatch.setattr(CompatService, "embed", _mock_embed_raise)
    client = TestClient(app)

    resp = client.post("/embed", json={"text": "hello"})

    assert resp.status_code == 500
    assert "error" in resp.json()
```

**Step 2: 运行测试验证失败**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -k "returns_500" -v`
Expected: FAIL — 返回 500 但无 `{"error": "..."}` body（FastAPI 默认返回 `{"detail": "Internal Server Error"}`）

**Step 3: 在 main.py 添加 logging import**

在 `main.py` 文件顶部（第 2 行附近）添加：

```python
import logging

logger = logging.getLogger(__name__)
```

放在 `import os` 和 `import uuid` 之间。

**Step 4: 为 ask_compat 添加 try-except**

将 `main.py:237-251` 的 `ask_compat` 改为：

```python
@app.post("/ask", response_model=dict)
async def ask_compat(request: AskCompatRequest) -> dict:
    """旧 /ask 兼容端点"""
    if not request.question:
        return JSONResponse(status_code=400, content={"error": "请求参数错误，缺少question字段"})
    from src.api.compat_service import CompatService

    try:
        service = CompatService()
        payload = await service.ask(
            question=request.question,
            user_id=request.user_id,
            top_k=request.top_k,
            display_name=request.display_name,
        )
        return JSONResponse(content=payload, media_type="application/json")
    except Exception as exc:
        logger.exception("/ask compat error")
        return JSONResponse(status_code=500, content={"error": str(exc)})
```

**Step 5: 为 clear_memory_compat 添加 try-except**

将 `main.py` 的 `clear_memory_compat` 改为：

```python
@app.post("/clear_memory", response_model=dict)
async def clear_memory_compat(request: ClearMemoryCompatRequest) -> dict:
    """旧 /clear_memory 兼容端点"""
    if not request.user_id:
        return JSONResponse(status_code=400, content={"error": "用户信息缺失"})
    from src.api.compat_service import CompatService

    try:
        service = CompatService()
        payload = await service.clear_memory(user_id=request.user_id)
        return JSONResponse(content=payload, media_type="application/json")
    except Exception as exc:
        logger.exception("/clear_memory compat error")
        return JSONResponse(status_code=500, content={"error": str(exc)})
```

**Step 6: 为 embed_compat 添加 try-except**

将 `main.py` 的 `embed_compat` 改为：

```python
@app.post("/embed", response_model=dict)
async def embed_compat(request: EmbedCompatRequest) -> dict:
    """旧 /embed 兼容端点"""
    if not request.text:
        return JSONResponse(status_code=400, content={"error": "请求参数错误，缺少text字段"})
    from src.api.compat_service import CompatService

    try:
        service = CompatService()
        embedding = await service.embed(text=request.text)
        return JSONResponse(content={"embedding": embedding}, media_type="application/json")
    except Exception as exc:
        logger.exception("/embed compat error")
        return JSONResponse(status_code=500, content={"error": str(exc)})
```

**Step 7: 运行异常处理测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -k "returns_500" -v`
Expected: ALL PASS

**Step 8: 运行全部测试确认无回归**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py tests/unit/test_config_compat.py tests/unit/test_memory_compat.py tests/integration/test_compat_endpoints.py -v`
Expected: ALL PASS
