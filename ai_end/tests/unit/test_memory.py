# tests/unit/test_memory.py
import pytest
from unittest.mock import AsyncMock, Mock
from src.db.memory import MemoryDB

# Hardcoded test UUIDs (DB requires UUID type for user_id)
UID_A = "00000000-0000-0000-0000-000000000001"
UID_B = "00000000-0000-0000-0000-000000000002"
UID_NX = "00000000-0000-0000-0000-000000000003"
UID_NEW = "00000000-0000-0000-0000-000000000004"


@pytest.mark.asyncio
async def test_save_and_get_profile():
    """测试保存和获取用户画像"""
    db = MemoryDB()

    # 保存画像
    await db.save_profile(UID_A, "内向、考研", "了解政策A")

    # 获取画像
    profile = await db.get_profile(UID_A)

    assert profile is not None
    assert str(profile["user_id"]) == UID_A
    assert profile["portrait_text"] == "内向、考研"
    assert profile["knowledge_text"] == "了解政策A"


@pytest.mark.asyncio
async def test_save_conversation():
    """测试保存对话历史"""
    db = MemoryDB()
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"}
    ]

    await db.save_conversation(UID_A, messages)

    result = await db.get_conversation(UID_A)

    assert result == messages


@pytest.mark.asyncio
async def test_get_nonexistent_profile():
    """测试获取不存在的画像"""
    db = MemoryDB()

    profile = await db.get_profile(UID_NX)

    assert profile is None


@pytest.mark.asyncio
async def test_append_conversation_uses_atomic_update(monkeypatch):
    db = MemoryDB()

    conn = AsyncMock()

    class _AcquireCtx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    pool = Mock()
    pool.acquire.return_value = _AcquireCtx()
    monkeypatch.setattr("src.db.memory.get_pool", AsyncMock(return_value=pool))

    new_messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你？"},
    ]
    await db.append_conversation(UID_A, new_messages, conversation_id="conv1")

    assert conn.execute.await_count == 2
    sql = conn.execute.await_args_list[0].args[0]
    assert "ON CONFLICT (user_id, conversation_id) DO UPDATE" in sql
    assert "|| EXCLUDED.messages" in sql


@pytest.mark.asyncio
async def test_ensure_user_exists_upserts_profile_and_conversation(monkeypatch):
    db = MemoryDB()

    conn = AsyncMock()

    class _AcquireCtx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    pool = Mock()
    pool.acquire.return_value = _AcquireCtx()
    monkeypatch.setattr("src.db.memory.get_pool", AsyncMock(return_value=pool))

    await db.ensure_user_exists(UID_NEW)

    assert conn.execute.await_count == 3
    first_sql = conn.execute.await_args_list[0].args[0]
    second_sql = conn.execute.await_args_list[1].args[0]
    third_sql = conn.execute.await_args_list[2].args[0]
    assert "INSERT INTO user_profiles" in first_sql
    assert "ON CONFLICT (user_id) DO NOTHING" in first_sql
    assert "INSERT INTO conversations" in second_sql
    assert "ON CONFLICT (user_id, conversation_id) DO NOTHING" in second_sql
    assert "INSERT INTO conversation_sessions" in third_sql


@pytest.mark.asyncio
async def test_create_and_get_session():
    """测试创建和获取会话"""
    db = MemoryDB()
    await db.create_session(UID_B, "conv1", "关于考研")

    session = await db.get_session(UID_B, "conv1")

    assert session is not None
    assert session["conversation_id"] == "conv1"
    assert session["title"] == "关于考研"


@pytest.mark.asyncio
async def test_list_user_sessions():
    """测试列出用户所有会话"""
    db = MemoryDB()
    await db.create_session(UID_B, "conv_list_1", "会话1")
    await db.create_session(UID_B, "conv_list_2", "会话2")

    sessions = await db.list_sessions(UID_B)
    session_ids = {s["conversation_id"] for s in sessions}

    assert "conv_list_1" in session_ids
    assert "conv_list_2" in session_ids


@pytest.mark.asyncio
async def test_save_conversation_to_session():
    """测试保存对话到指定会话"""
    db = MemoryDB()
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]

    await db.save_conversation(UID_B, messages, conversation_id="conv_save")
    result = await db.get_conversation(UID_B, conversation_id="conv_save")

    assert result == messages


@pytest.mark.asyncio
async def test_update_session_title():
    """测试更新会话标题"""
    db = MemoryDB()
    await db.create_session(UID_B, "conv_title", "旧标题")
    await db.update_session_title(UID_B, "conv_title", "新标题")

    session = await db.get_session(UID_B, "conv_title")
    assert session is not None
    assert session["title"] == "新标题"
