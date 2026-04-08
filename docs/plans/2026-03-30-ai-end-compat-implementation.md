# AI End 旧接口兼容改造 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不修改 backend 代码的前提下，让 ai_end_refactor 兼容旧 ai_end 的 `/ask`、`/clear_memory`、`/embed` JSON 协议与关键错误语义。

**Architecture:** 新增兼容 API 路由与兼容编排服务，复用现有 MemoryDB、ChatClient、embedding 能力。`/ask` 内部消费 ChatClient 事件流并聚合为单次 JSON，按 user_id 条件输出会话扩展字段。时区采用“环境变量 > 配置字段 > PG 会话时区”的优先级确定当天边界。

**Tech Stack:** Python 3.11, FastAPI, asyncpg, pytest, pytest-asyncio

---

### Task 1: 新增兼容接口契约测试（RED）

**Files:**
- Create: `ai_end_refactor/tests/integration/test_compat_endpoints.py`
- Test: `ai_end_refactor/tests/integration/test_compat_endpoints.py`

**Step 1: 写 `/ask` 缺参失败测试**

```python
from fastapi.testclient import TestClient


def test_ask_returns_400_when_question_missing():
    from src.api.main import app
    client = TestClient(app)

    resp = client.post("/ask", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "请求参数错误，缺少question字段"}
```

**Step 2: 写 `/clear_memory` 缺 user_id 失败测试**

```python
def test_clear_memory_returns_400_when_user_id_missing():
    from src.api.main import app
    client = TestClient(app)

    resp = client.post("/clear_memory", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "用户信息缺失"}
```

**Step 3: 写 `/embed` 缺 text 失败测试**

```python
def test_embed_returns_400_when_text_missing():
    from src.api.main import app
    client = TestClient(app)

    resp = client.post("/embed", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "请求参数错误，缺少text字段"}
```

**Step 4: 运行测试确认失败**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -v`
Expected: FAIL（路由尚未实现）

---

### Task 2: 实现兼容 API 路由骨架（GREEN）

**Files:**
- Modify: `ai_end_refactor/src/api/main.py`
- Create: `ai_end_refactor/src/api/compat_models.py`
- Test: `ai_end_refactor/tests/integration/test_compat_endpoints.py`

**Step 1: 新增兼容请求模型（最小字段）**

```python
from pydantic import BaseModel


class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None


class ClearMemoryCompatRequest(BaseModel):
    user_id: str | None = None


class EmbedCompatRequest(BaseModel):
    text: str | None = None
```

**Step 2: 在 `main.py` 新增 3 个兼容路由（先返回占位成功/失败）**

```python
@app.post("/ask", response_model=dict)
async def ask_compat(request: AskCompatRequest) -> dict:
    if not request.question:
        return JSONResponse(status_code=400, content={"error": "请求参数错误，缺少question字段"})
    return {"answer": "", "related_articles": []}
```

**Step 3: 新增 `/clear_memory`、`/embed` 参数校验分支**

```python
if not request.user_id:
    return JSONResponse(status_code=400, content={"error": "用户信息缺失"})
```

**Step 4: 运行测试确认基本契约通过**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -v`
Expected: PASS（基础缺参行为通过，后续再补完整语义）

---

### Task 3: 会话与时区能力扩展（RED -> GREEN）

**Files:**
- Modify: `ai_end_refactor/src/db/memory.py`
- Create: `ai_end_refactor/tests/unit/test_memory_compat.py`
- Modify: `ai_end_refactor/src/config/settings.py`
- Create: `ai_end_refactor/tests/unit/test_config_compat.py`

**Step 1: 先写时区优先级测试（RED）**

```python
def test_resolve_compat_timezone_prefers_env(monkeypatch):
    monkeypatch.setenv("AI_COMPAT_TZ", "Asia/Shanghai")
    cfg = Config.load()
    assert cfg.ai_compat_timezone == "Asia/Shanghai"
```

**Step 2: 先写“当天最新会话”查询测试（RED）**

```python
@pytest.mark.asyncio
async def test_get_latest_session_in_range_returns_newest(monkeypatch):
    # mock conn.fetchrow returns latest row
    ...
    assert result["conversation_id"] == "c-latest"
```

**Step 3: 在 `settings.py` 增加 `ai_compat_timezone` 配置读取**

```python
ai_compat_timezone = os.getenv("AI_COMPAT_TZ") or os.getenv("AI_COMPAT_TIMEZONE")
```

**Step 4: 在 `memory.py` 增加能力方法**

```python
async def get_latest_session_in_utc_range(self, user_id: str, start_utc: datetime, end_utc: datetime) -> dict[str, Any] | None:
    ...
```

**Step 5: 运行测试验证通过**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_memory_compat.py tests/unit/test_config_compat.py -v`
Expected: PASS

---

### Task 4: 新增兼容编排服务（RED -> GREEN）

**Files:**
- Create: `ai_end_refactor/src/api/compat_service.py`
- Create: `ai_end_refactor/tests/unit/test_compat_service.py`

**Step 1: 写 `/ask` 编排单测（RED）**

```python
@pytest.mark.asyncio
async def test_ask_with_user_id_returns_conversation_fields(monkeypatch):
    service = CompatService(...)
    result = await service.ask(question="q", user_id="u1")
    assert "answer" in result
    assert "related_articles" in result
    assert "conversation_id" in result
    assert "session_created" in result
```

**Step 2: 写无 user_id 字段裁剪测试（RED）**

```python
@pytest.mark.asyncio
async def test_ask_without_user_id_omits_conversation_fields(monkeypatch):
    result = await service.ask(question="q", user_id=None)
    assert "conversation_id" not in result
    assert "session_created" not in result
```

**Step 3: 实现 `CompatService.ask` 最小逻辑**

```python
class CompatService:
    async def ask(...):
        # 1) session resolve
        # 2) runtime hint build
        # 3) collect chat events
        # 4) return compat payload
```

**Step 4: 实现 `clear_memory` 新语义**

```python
async def clear_memory(self, user_id: str) -> dict[str, Any]:
    conversation_id = await self._create_session(user_id)
    return {"cleared": True, "conversation_id": conversation_id}
```

**Step 5: 运行单测**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: PASS

---

### Task 5: `/ask` 运行时提示与 top_k/display_name 规则（RED -> GREEN）

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py`
- Modify: `ai_end_refactor/tests/unit/test_compat_service.py`

**Step 1: 写 top_k 合法/非法测试（RED）**

```python
def test_build_runtime_hints_ignores_invalid_top_k():
    hints = build_runtime_hints(top_k="abc", display_name=None)
    assert "top_k" not in hints
```

**Step 2: 写 display_name 注入测试（RED）**

```python
def test_build_runtime_hints_includes_display_name_hint():
    hints = build_runtime_hints(top_k=None, display_name="张三")
    assert "可酌情称呼" in hints
```

**Step 3: 实现提示构建函数并接入 ask 流程**

```python
def build_runtime_hints(...):
    ...
```

**Step 4: 运行单测**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: PASS

---

### Task 6: 接入路由到 CompatService，并固定 JSON 输出（GREEN）

**Files:**
- Modify: `ai_end_refactor/src/api/main.py`
- Modify: `ai_end_refactor/tests/integration/test_compat_endpoints.py`

**Step 1: 在路由中调用 `CompatService`**

```python
service = CompatService()
payload = await service.ask(...)
return JSONResponse(content=payload, media_type="application/json")
```

**Step 2: 新增 content-type 断言测试**

```python
def test_ask_returns_application_json_content_type():
    ...
    assert resp.headers["content-type"].startswith("application/json")
```

**Step 3: 运行集成测试**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -v`
Expected: PASS

---

### Task 7: `/embed` 复用 embedding 能力并补齐失败语义（RED -> GREEN）

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py`
- Modify: `ai_end_refactor/src/api/main.py`
- Modify: `ai_end_refactor/tests/integration/test_compat_endpoints.py`

**Step 1: 写 `/embed` 成功与失败测试（RED）**

```python
def test_embed_success(monkeypatch):
    monkeypatch.setattr("src.core.base_retrieval.generate_embedding", _fake)
    ...
    assert resp.json()["embedding"] == [0.1, 0.2]
```

**Step 2: 实现 `/embed` 复用逻辑**

```python
embedding = await generate_embedding(text)
return {"embedding": embedding}
```

**Step 3: 运行集成测试**

Run: `cd ai_end_refactor && uv run pytest tests/integration/test_compat_endpoints.py -v`
Expected: PASS

---

### Task 8: 全量回归、文档同步与交付

**Files:**
- Modify: `ai_end_refactor/API_GUIDE.md`
- Modify: `ai_end_refactor/README.md`
- Modify: `docs/plans/2026-03-30-ai-end-compat-design.md`（如实现后有轻微偏差需回填）

**Step 1: 更新 API 文档（新增兼容端点说明）**

```markdown
POST /ask
POST /clear_memory
POST /embed
```

**Step 2: 运行核心测试集**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py tests/integration/test_compat_endpoints.py tests/unit/test_api_main.py tests/integration/test_concurrency_regression.py -v`
Expected: PASS

**Step 3: 运行全量测试（可选但建议）**

Run: `cd ai_end_refactor && uv run pytest -v`
Expected: PASS

---

## 执行注意事项

1. 遵循 TDD：每个行为先写失败测试，再最小实现，再回归。
2. 兼容层只处理协议与编排，不把业务逻辑分散到路由中。
3. `backend` 目录保持不改，切换仅依赖 `AI_END_URL`。
4. `/health` 不在本次改造范围。
