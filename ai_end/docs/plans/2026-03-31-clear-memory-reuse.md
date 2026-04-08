# clear_memory 智能会话复用 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** clear_memory 查询当天最新会话，有消息则创建新会话，无消息则复用，始终返回 {"cleared": True, "conversation_id": "..."}。

**Architecture:** 在 MemoryDB 新增 `get_latest_session_with_messages` 方法（LEFT JOIN 两表查消息状态），在 CompatService.clear_memory 中基于查询结果做三路判断。不影响 `_resolve_session` 和 `/ask`。

**Tech Stack:** Python 3.11+, asyncpg, pytest, pytest-asyncio

---

## Task 1: _FakeMemoryDB 扩展 — 支持 messages 数据

**Files:**
- Modify: `ai_end_refactor/tests/unit/test_compat_service.py:46-63`

**Step 1: 扩展 _FakeMemoryDB 支持新方法**

在 `_FakeMemoryDB` 中添加 `get_latest_session_with_messages` 方法，通过 `_latest_session` dict 中的 `messages` 字段返回数据。

```python
class _FakeMemoryDB:
    """可编程的 MemoryDB 替身。"""

    def __init__(
        self,
        latest_session: dict | None = None,
    ):
        self._latest_session = latest_session
        self._created_sessions: list[tuple[str, str]] = []

    async def get_latest_session_in_utc_range(self, user_id, start_utc, end_utc):
        return self._latest_session

    async def get_latest_session_with_messages(self, user_id, start_utc, end_utc):
        return self._latest_session

    async def create_session(self, user_id, conversation_id, title="新会话"):
        self._created_sessions.append((user_id, conversation_id))

    async def ensure_user_exists(self, user_id):
        pass
```

**Step 2: 运行现有测试确认不破坏**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: 全部 PASS（新方法是纯新增，不影响现有行为）

---

## Task 2: clear_memory 测试 — 四个场景

**Files:**
- Modify: `ai_end_refactor/tests/unit/test_compat_service.py` (TestCompatServiceClearMemory 类)

**Step 1: 重写 TestCompatServiceClearMemory，覆盖四个场景**

在现有 `test_clear_memory_creates_new_session` 和 `test_clear_memory_without_user_id_raises` 的基础上，新增两个测试并调整现有测试：

```python
class TestCompatServiceClearMemory:
    """CompatService.clear_memory 测试"""

    @pytest.mark.asyncio
    async def test_clear_memory_creates_new_when_today_session_has_messages(self, monkeypatch):
        """当天会话存在且有消息 → 创建新会话。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "existing-conv",
            "user_id": "u1",
            "title": "旧会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [{"role": "user", "content": "hello"}],
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert "conversation_id" in result
        assert result["conversation_id"] != "existing-conv"
        assert len(fake_memory._created_sessions) == 1

    @pytest.mark.asyncio
    async def test_clear_memory_reuses_when_today_session_has_no_messages(self, monkeypatch):
        """当天会话存在但无消息 → 复用该会话，不创建新的。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "empty-conv",
            "user_id": "u1",
            "title": "空会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [],
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert result["conversation_id"] == "empty-conv"
        assert len(fake_memory._created_sessions) == 0

    @pytest.mark.asyncio
    async def test_clear_memory_creates_new_when_no_today_session(self, monkeypatch):
        """无当天会话 → 创建新会话。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session=None)

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert "conversation_id" in result
        assert len(result["conversation_id"]) == 8
        assert len(fake_memory._created_sessions) == 1

    @pytest.mark.asyncio
    async def test_clear_memory_without_user_id_raises(self, monkeypatch):
        """无 user_id 时 clear_memory 应抛出异常。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        service = CompatService(config=config)

        with pytest.raises(ValueError):
            await service.clear_memory(user_id=None)
```

**Step 2: 运行测试确认全部失败（RED）**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestCompatServiceClearMemory -v`
Expected: 4 个测试中至少 3 个 FAIL（`test_clear_memory_creates_new_when_today_session_has_messages` 和 `test_clear_memory_reuses_when_today_session_has_no_messages` 依赖新逻辑；`test_clear_memory_creates_new_when_no_today_session` 依赖调用新方法；`test_clear_memory_without_user_id_raises` 应该 PASS）

---

## Task 3: MemoryDB 新增 get_latest_session_with_messages

**Files:**
- Modify: `ai_end_refactor/src/db/memory.py` (在 `get_latest_session_in_utc_range` 之后)

**Step 1: 实现新方法**

在 `get_latest_session_in_utc_range` 方法（第 163 行）之后添加：

```python
async def get_latest_session_with_messages(
    self,
    user_id: str,
    start_utc: datetime,
    end_utc: datetime,
) -> dict[str, Any] | None:
    """查询当天最新会话及其消息状态。

    LEFT JOIN conversations 表获取 messages 字段，
    用于判断会话是否有消息（clear_memory 空会话复用）。
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cs.user_id, cs.conversation_id, cs.title,
                   cs.created_at, cs.updated_at,
                   COALESCE(c.messages, '[]'::jsonb) AS messages
            FROM conversation_sessions cs
            LEFT JOIN conversations c
                ON c.user_id = cs.user_id AND c.conversation_id = cs.conversation_id
            WHERE cs.user_id = $1 AND cs.created_at >= $2 AND cs.created_at < $3
            ORDER BY cs.created_at DESC
            LIMIT 1
            """,
            user_id,
            start_utc,
            end_utc,
        )
        return dict(row) if row else None
```

**Step 2: 运行测试**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py::TestCompatServiceClearMemory -v`
Expected: 仍然 FAIL（clear_memory 尚未调用新方法）

---

## Task 4: 重写 clear_memory 方法

**Files:**
- Modify: `ai_end_refactor/src/api/compat_service.py:284-305`

**Step 1: 替换 clear_memory 实现**

将 `compat_service.py` 第 284-305 行的 `clear_memory` 方法替换为：

```python
async def clear_memory(self, user_id: str | None = None) -> dict[str, Any]:
    """兼容旧 /clear_memory 接口：创建或复用当天会话。

    查询当天最新会话：
      1. 会话存在且有消息 → 创建新会话
      2. 会话存在但无消息 → 复用现有会话
      3. 无当天会话 → 创建新会话

    Args:
        user_id: 用户 ID（必须提供）。

    Returns:
        ``{"cleared": True, "conversation_id": "..."}``

    Raises:
        ValueError: user_id 为 None 时
    """
    if not user_id:
        raise ValueError("clear_memory requires a user_id")

    db = self._create_memory_db()
    start_utc, end_utc = _today_range()

    session = await db.get_latest_session_with_messages(
        user_id, start_utc, end_utc,
    )

    if session:
        messages = session.get("messages")
        # messages 可能为 None（LEFT JOIN 未匹配）或空列表
        if messages:
            # 有消息 → 创建新会话
            new_id = uuid.uuid4().hex[:8]
            await db.create_session(user_id, new_id, "新会话")
            return {"cleared": True, "conversation_id": new_id}
        else:
            # 无消息 → 复用
            return {"cleared": True, "conversation_id": session["conversation_id"]}

    # 无当天会话 → 创建新的
    new_id = uuid.uuid4().hex[:8]
    await db.create_session(user_id, new_id, "新会话")
    return {"cleared": True, "conversation_id": new_id}
```

**Step 2: 运行全部测试（GREEN）**

Run: `cd ai_end_refactor && uv run pytest tests/unit/test_compat_service.py -v`
Expected: 全部 PASS

---

## Task 5: 全量回归测试

**Step 1: 运行整个项目测试**

Run: `cd ai_end_refactor && uv run pytest tests/ -v`
Expected: 全部 PASS，确认无破坏性变更

**Step 2: 代码检查**

Run: `cd ai_end_refactor && uv run ruff check src/ tests/`
Expected: 无报错
