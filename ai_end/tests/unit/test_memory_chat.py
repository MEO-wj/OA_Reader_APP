import uuid
from unittest.mock import AsyncMock

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
        '{"confirmed": {"identity": [], "interests": ["喜欢科研"], "constraints": ["内向"]}, "hypothesized": {"identity": [], "interests": []}}',
        '{"confirmed_facts": ["了解学硕政策"], "pending_queries": []}',
    )

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "new_conv"

    async for _ in client.chat_stream_async("你好"):
        pass

    # 验证画像融入主 system prompt（索引0）
    assert client.messages[0]["role"] == "system"
    # 验证画像结构化章节被正确注入
    assert "已确认约束" in client.messages[0]["content"]
    assert "内向" in client.messages[0]["content"]


@pytest.mark.asyncio
async def test_new_session_emits_memory_injection_debug_event():
    """新会话应输出画像注入调试事件，便于前端定位条件命中情况。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("new_session_2")
    await db.save_profile(
        user_id,
        '{"confirmed": {"identity": [], "interests": [], "constraints": ["理性执行"]}, "hypothesized": {"identity": [], "interests": []}}',
        '{"confirmed_facts": ["了解调剂规则"], "pending_queries": []}',
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
    assert "confirmed" in message
    assert "你是一个智能校园 OA 助手" in details.get("system_prompt_full", "")
    assert "已确认约束" in details.get("system_prompt_full", "")


@pytest.mark.asyncio
async def test_new_session_memory_prompt_sanitizes_think_and_noise():
    """画像注入到 system message 前应去除 think 标签和无用符号。"""
    config = Config.load()
    db = MemoryDB()
    user_id = _uid("new_session_3")
    await db.save_profile(
        user_id,
        '<think>internal notes</think>{"confirmed": {"identity": [], "interests": [], "constraints": ["执行强"]}, "hypothesized": {"identity": [], "interests": []}}',
        '{"confirmed_facts": ["已了解政策"], "pending_queries": []}',
    )

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "new_conv"

    async for _ in client.chat_stream_async("你好"):
        pass

    # 验证画像融入主 system prompt
    memory_prompt = client.messages[0]["content"]
    assert "已确认约束" in memory_prompt
    assert "执行强" in memory_prompt
    assert "<think>" not in memory_prompt


@pytest.mark.asyncio
async def test_chat_stream_passes_user_id_to_build_tools_definition(monkeypatch):
    config = Config.load()
    client = ChatClient(config)
    client.user_id = _uid("tools_pass")

    captured = {}
    original = client.skill_system.build_tools_definition

    def wrapped(*args, **kwargs):
        captured.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(client.skill_system, "build_tools_definition", wrapped)

    # Mock API stream to avoid network dependency
    async def _fake_stream(messages, tools):
        yield type("Chunk", (), {"usage": None, "choices": [type("Choice", (), {"delta": type("Delta", (), {"content": "hi", "tool_calls": None})()})()]})()

    monkeypatch.setattr(client, "_create_completion_stream_async", _fake_stream)

    async for event in client.chat_stream_async("hello"):
        if event.get("type") == "done":
            break

    assert captured.get("user_id") == _uid("tools_pass")


# ──────────────────────────────────────────────────────
# Task 1: 系统提示词日期占位符
# ──────────────────────────────────────────────────────


def test_system_prompt_template_contains_date_placeholders():
    """系统提示词模板应包含 {current_date} 和 {weekday} 占位符。"""
    from src.chat.prompts_runtime import SYSTEM_PROMPT_TEMPLATE

    assert "当前日期：{current_date}（{weekday}）" in SYSTEM_PROMPT_TEMPLATE


# ──────────────────────────────────────────────────────
# Task 2: ChatClient 注入当前日期
# ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_system_prompt_injects_current_date_and_weekday(monkeypatch):
    """_build_system_prompt() 应注入正确的当前日期和中文星期。"""
    import dataclasses
    from datetime import datetime
    from zoneinfo import ZoneInfo

    base_config = Config.load()
    config = dataclasses.replace(base_config, compat_timezone="Asia/Shanghai")

    client = ChatClient(config)

    # Mock _get_now via monkeypatch: client.py uses a helper that we can patch
    fixed_dt = datetime(2026, 4, 9, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    import src.chat.client as client_mod
    monkeypatch.setattr(client_mod, "_get_now", lambda tz=None: fixed_dt)

    prompt = client._build_system_prompt()

    assert "当前日期：2026-04-09（星期四）" in prompt


# ──────────────────────────────────────────────────────
# Task 4: force_memory_after_turn — 回合末强制裁决与状态清理
# ──────────────────────────────────────────────────────

def _make_chunk(content="hi", tool_calls=None, usage=None):
    """快速构建一个 LLM stream chunk 对象。"""
    delta = type("Delta", (), {"content": content, "tool_calls": tool_calls})()
    choice = type("Choice", (), {"delta": delta})()
    return type("Chunk", (), {"usage": usage, "choices": [choice]})()


def _make_tool_call_chunk(call_id, func_name, arguments, index=0):
    """构建一个增量式 tool_call delta chunk。"""
    fn = type("Fn", (), {"name": func_name, "arguments": arguments})()
    tc = type("TC", (), {"index": index, "id": call_id, "function": fn})()
    delta = type("Delta", (), {"content": None, "tool_calls": [tc]})()
    choice = type("Choice", (), {"delta": delta})()
    return type("Chunk", (), {"usage": None, "choices": [choice]})()


def _patch_client_for_stream_test(monkeypatch, client):
    """为 chat_stream_async 测试统一 mock 数据库依赖。"""
    # 避免 _history_manager.append 触发真实 DB 写入
    monkeypatch.setattr(
        client._history_manager, "append",
        AsyncMock(return_value=None),
    )
    # 避免 load_context 触发真实 DB 读取
    monkeypatch.setattr(
        client, "load_context",
        AsyncMock(return_value=[]),
    )


@pytest.mark.asyncio
async def test_force_memory_after_turn_bypasses_threshold(monkeypatch):
    """force_memory_after_turn=True 时，即使未达 5 条门槛也执行 form_memory。"""
    config = Config.load()
    user_id = _uid("force_bypass")

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "c_force"
    # 只有一条 user（远低于 5 条门槛）
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    # 手动置位强制标记，模拟 tool call 中 form_memory 已触发
    client._force_memory_after_turn = True

    _patch_client_for_stream_test(monkeypatch, client)

    form_memory_called = False

    async def _fake_form_memory():
        nonlocal form_memory_called
        form_memory_called = True

    monkeypatch.setattr(client, "form_memory", _fake_form_memory)

    # Mock stream: AI 直接回复，无 tool_calls
    async def _fake_stream(messages, tools):
        yield _make_chunk(content="reply")

    monkeypatch.setattr(client, "_create_completion_stream_async", _fake_stream)

    async for _ in client.chat_stream_async("test"):
        pass

    assert form_memory_called is True, "force_memory_after_turn=True 应绕过门槛执行 form_memory"


@pytest.mark.asyncio
async def test_force_memory_only_once_despite_multiple_form_memory_calls(monkeypatch):
    """同一回合多次 form_memory tool_call 仍仅执行一次 form_memory。"""
    config = Config.load()
    user_id = _uid("force_once")

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "c_once"
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    _patch_client_for_stream_test(monkeypatch, client)

    form_memory_call_count = 0

    async def _fake_form_memory():
        nonlocal form_memory_call_count
        form_memory_call_count += 1

    monkeypatch.setattr(client, "form_memory", _fake_form_memory)

    # Mock handle_tool_calls: 模拟两个 form_memory tool_call 都触发了 mark callback
    async def _fake_handle_tool_calls(tool_calls):
        # 模拟两次 form_memory 调用都触发了 mark callback（幂等）
        client._force_memory_after_turn = True
        client._force_memory_after_turn = True
        return [{"role": "tool", "tool_call_id": "tc1", "content": "ok"}]

    monkeypatch.setattr(client, "_handle_tool_calls_async", _fake_handle_tool_calls)

    # 第一轮返回 tool_calls（用增量式 chunk），第二轮直接回复
    call_count = 0

    async def _fake_stream(messages, tools):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # 用增量式 tool_call chunk 模拟真实 LLM 流式返回
            yield _make_tool_call_chunk("tc1", "form_memory", '{"reason":"test"}', index=0)
        else:
            yield _make_chunk(content="final reply")

    monkeypatch.setattr(client, "_create_completion_stream_async", _fake_stream)

    async for _ in client.chat_stream_async("test"):
        pass

    assert form_memory_call_count == 1, "多次 form_memory tool_call 应只执行一次 form_memory"


@pytest.mark.asyncio
async def test_force_memory_flag_cleared_after_turn(monkeypatch):
    """成功/失败后标记都会清零。"""
    config = Config.load()
    user_id = _uid("force_clear")

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "c_clear"
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    client._force_memory_after_turn = True

    _patch_client_for_stream_test(monkeypatch, client)

    async def _fake_form_memory():
        pass  # 成功执行

    monkeypatch.setattr(client, "form_memory", _fake_form_memory)

    async def _fake_stream(messages, tools):
        yield _make_chunk(content="reply")

    monkeypatch.setattr(client, "_create_completion_stream_async", _fake_stream)

    async for _ in client.chat_stream_async("test"):
        pass

    assert client._force_memory_after_turn is False, "回合结束后标记应清零"


@pytest.mark.asyncio
async def test_force_memory_flag_cleared_even_on_form_memory_failure(monkeypatch):
    """form_memory 抛异常后标记清零且不中断对话，done 事件正常发送。"""
    config = Config.load()
    user_id = _uid("force_clear_err")

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "c_clear_err"
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    client._force_memory_after_turn = True

    _patch_client_for_stream_test(monkeypatch, client)

    async def _fake_form_memory():
        raise RuntimeError("form_memory failed!")

    monkeypatch.setattr(client, "form_memory", _fake_form_memory)

    async def _fake_stream(messages, tools):
        yield _make_chunk(content="reply")

    monkeypatch.setattr(client, "_create_completion_stream_async", _fake_stream)

    events = []
    async for event in client.chat_stream_async("test"):
        events.append(event)

    # 标记已清零
    assert client._force_memory_after_turn is False
    # done 事件正常发送，异常不中断对话
    assert any(e.get("type") == "done" for e in events)


@pytest.mark.asyncio
async def test_no_force_memory_retains_threshold_behavior(monkeypatch):
    """未置位 _force_memory_after_turn 时仍保留 5 条门槛行为。"""
    config = Config.load()
    user_id = _uid("no_force")

    client = ChatClient(config)
    client.user_id = user_id
    client.conversation_id = "c_no_force"
    # 消息数很少（低于 5 条门槛）
    client.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    _patch_client_for_stream_test(monkeypatch, client)

    form_memory_called = False

    async def _fake_form_memory():
        nonlocal form_memory_called
        form_memory_called = True

    monkeypatch.setattr(client, "form_memory", _fake_form_memory)

    async def _fake_stream(messages, tools):
        yield _make_chunk(content="reply")

    monkeypatch.setattr(client, "_create_completion_stream_async", _fake_stream)

    async for _ in client.chat_stream_async("test"):
        pass

    assert form_memory_called is False, "未置位且未达门槛时不应执行 form_memory"
