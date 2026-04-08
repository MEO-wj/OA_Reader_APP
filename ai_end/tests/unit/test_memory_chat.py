import uuid

import pytest

from src.chat.client import ChatClient
from src.config.settings import Config
from src.core.db import get_pool
from src.db.memory import MemoryDB

# 确定性 UUID 生成：从 seed 字符串派生可复现的 UUID v5
_TEST_UUID_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_used_uids: set[str] = set()


def _uid(suffix: str) -> str:
    """根据 suffix 生成确定性 UUID，并自动注册到清理集合。"""
    uid = str(uuid.uuid5(_TEST_UUID_NAMESPACE, f"memory_chat_{suffix}"))
    _used_uids.add(uid)
    return uid


async def _cleanup_test_users() -> None:
    """使用 = ANY($1::uuid[]) 精确清理已注册的测试 UUID。"""
    if not _used_uids:
        return
    pool = await get_pool()
    uid_list = list(_used_uids)
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM conversation_sessions WHERE user_id = ANY($1::uuid[])",
            uid_list,
        )
        await conn.execute(
            "DELETE FROM conversations WHERE user_id = ANY($1::uuid[])",
            uid_list,
        )
        await conn.execute(
            "DELETE FROM user_profiles WHERE user_id = ANY($1::uuid[])",
            uid_list,
        )


@pytest.fixture(autouse=True)
async def isolate_memory_chat_db():
    await _cleanup_test_users()
    _used_uids.clear()
    yield
    await _cleanup_test_users()
    _used_uids.clear()


@pytest.mark.asyncio
async def test_chat_client_with_user_id():
    """测试带 user_id 的客户端初始化"""
    config = Config.load()
    user_id = _uid("init_user")

    client = await ChatClient.create(config, user_id=user_id)

    assert client.user_id == user_id
    assert client.messages == []
    assert client.round_count == 0


@pytest.mark.asyncio
async def test_chat_client_with_conversation_id():
    """测试带 conversation_id 的客户端初始化"""
    config = Config.load()
    user_id = _uid("init_conv")

    client = await ChatClient.create(
        config,
        user_id=user_id,
        conversation_id="conv123",
    )

    assert client.user_id == user_id
    assert client.conversation_id == "conv123"


@pytest.mark.asyncio
async def test_load_context_uses_conversation_id():
    """测试 load_context 按会话读取历史并返回列表"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("load_ctx_1")
    conversation_id = "conv_test"
    history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]
    await db.save_conversation(user_id, history, conversation_id=conversation_id)

    client = await ChatClient.create(
        config,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    context = await client.load_context()

    assert isinstance(context, list)
    assert context == history


@pytest.mark.asyncio
async def test_load_context_returns_message_list():
    """load_context 应返回对话历史列表，不含 system prompt。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("load_ctx_2")
    conversation_id = "conv_test"
    history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]
    await db.save_conversation(user_id, history, conversation_id=conversation_id)

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = conversation_id

    result = await client.load_context()
    assert isinstance(result, list)
    assert result == history
    assert "【用户画像】" not in str(result)


@pytest.mark.asyncio
async def test_message_order_preserved_when_loading_incremental_history():
    """验证顺序保持 ABABAB -> ABABABA，不出现错序/重复。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("order")
    conversation_id = "c1"
    db_history = [
        {"role": "user", "content": "用户1"},
        {"role": "assistant", "content": "助手1"},
        {"role": "user", "content": "用户2"},
        {"role": "assistant", "content": "助手2"},
    ]
    await db.save_conversation(user_id, db_history, conversation_id=conversation_id)

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = conversation_id
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "用户1"},
        {"role": "assistant", "content": "助手1"},
        {"role": "user", "content": "用户2"},
    ]

    async for _ in client.chat_stream_async("用户3"):
        pass

    assert client.messages[1]["content"] == "用户1"
    assert client.messages[2]["content"] == "助手1"
    assert client.messages[3]["content"] == "用户2"
    assert client.messages[4]["content"] == "助手2"
    assert client.messages[5]["content"] == "用户3"


@pytest.mark.asyncio
async def test_form_memory_does_not_clear_history():
    """form_memory 触发后不应修改 messages。"""
    config = Config.load()
    user_id = _uid("form_memory")

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "c1"
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "用户1"},
        {"role": "assistant", "content": "助手1"},
    ]
    original_messages = list(client.messages)

    await client.form_memory()

    assert client.messages == original_messages


@pytest.mark.asyncio
async def test_new_session_loads_profile_as_second_system_message():
    """新会话应把画像融入主 system message。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("new_session_1")
    await db.save_profile(
        user_id,
        '{"hard_constraints": ["内向"], "soft_constraints": ["喜欢科研"], "risk_tolerance": []}',
        '{"verified_facts": ["了解学硕政策"], "pending_queries": []}',
    )

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "new_conv"

    async for _ in client.chat_stream_async("你好"):
        pass

    # 验证画像融入主 system prompt（索引0）
    assert client.messages[0]["role"] == "system"
    # 验证画像结构化章节被正确注入
    assert "<必须满足>" in client.messages[0]["content"]
    assert "内向" in client.messages[0]["content"]


@pytest.mark.asyncio
async def test_new_session_emits_memory_injection_debug_event():
    """新会话应输出画像注入调试事件，便于前端定位条件命中情况。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("new_session_2")
    await db.save_profile(
        user_id,
        '{"hard_constraints": ["理性执行"], "soft_constraints": [], "risk_tolerance": []}',
        '{"verified_facts": ["了解调剂规则"], "pending_queries": []}',
    )

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "new_conv"

    events = []
    async for event in client.chat_stream_async("你好"):
        events.append(event)

    debug_events = [
        e for e in events
        if e.get("type") == "db_operation" and e.get("operation") == "memory_injection_check"
    ]
    assert len(debug_events) == 1
    details = debug_events[0].get("details", {})
    assert details.get("is_new_runtime_session") is True
    assert details.get("history_empty") is True
    assert details.get("profile_loaded") is True
    assert details.get("profile_injected") is True
    message = debug_events[0].get("message", "")
    assert "SYSTEM_PROMPT_FULL" in message
    assert "hard_constraints" in message
    assert "你是一个通用 AI Agent 助手。" in details.get("system_prompt_full", "")
    assert "必须满足" in details.get("system_prompt_full", "")


@pytest.mark.asyncio
async def test_new_session_memory_prompt_sanitizes_think_and_noise():
    """画像注入到 system message 前应去除 think 标签和无用符号。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("new_session_3")
    await db.save_profile(
        user_id,
        '<think>internal notes</think>{"hard_constraints": ["执行强"], "soft_constraints": [], "risk_tolerance": []}',
        '{"verified_facts": ["已了解政策"], "pending_queries": []}',
    )

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "new_conv"

    async for _ in client.chat_stream_async("你好"):
        pass

    # 验证画像融入主 system prompt
    memory_prompt = client.messages[0]["content"]
    assert "<必须满足>" in memory_prompt
    assert "执行强" in memory_prompt
    assert "<think>" not in memory_prompt

