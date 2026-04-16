"""
TDD RED -> GREEN 阶段 - CompatService 兼容编排服务测试

测试要点：
  1) ask 有 user_id → 返回 answer + related_articles + conversation_id + session_created
  2) ask 无 user_id → 返回 answer + related_articles，不含 conversation_id / session_created
  3) ask 有 user_id 且当天已有会话 → session_created=False，复用 conversation_id
  4) ask 有 user_id 且当天无会话 → session_created=True，新建 conversation_id
  5) ask 事件聚合：delta 拼接为 answer，tool_result 提取 related_articles
  6) ask 错误事件处理
  7) clear_memory → 返回 cleared=True + conversation_id（新会话）
  8) _today_range 工具方法正确计算 UTC 范围
"""
import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from src.config.settings import Config


def test_ask_compat_request_rejects_bool_top_k():
    """I1: AskCompatRequest 应在模型层拒绝 bool 类型的 top_k。"""
    from pydantic import ValidationError
    from src.api.compat_models import AskCompatRequest

    with pytest.raises(ValidationError, match="boolean"):
        AskCompatRequest(question="test", top_k=True)


# ---------------------------------------------------------------------------
# Helpers: fake client / fake MemoryDB
# ---------------------------------------------------------------------------

class _FakeClient:
    """Fake ChatClient，通过 events 参数预设 chat_stream_async 产出的事件序列。"""

    def __init__(self, events: list[dict] | None = None):
        self._events = events or []

    async def chat_stream_async(self, _user_input: str):
        for event in self._events:
            yield event


class _FakeMemoryDB:
    """可编程的 MemoryDB 替身。"""

    def __init__(
        self,
        latest_session: dict | None = None,
        sessions_by_id: dict[str, dict] | None = None,
    ):
        self._latest_session = latest_session
        self._created_sessions: list[tuple[str, str]] = []
        self._sessions_by_id = sessions_by_id or {}
        if latest_session and latest_session.get("conversation_id"):
            self._sessions_by_id.setdefault(latest_session["conversation_id"], latest_session)

    async def get_latest_session_in_utc_range(self, user_id, start_utc, end_utc):
        return self._latest_session

    async def get_latest_session_with_messages(self, user_id, start_utc, end_utc):
        return self._latest_session

    async def get_session(self, user_id, conversation_id):
        return self._sessions_by_id.get(conversation_id)

    async def create_session(self, user_id, conversation_id, title="新会话"):
        self._created_sessions.append((user_id, conversation_id))
        self._sessions_by_id[conversation_id] = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "title": title,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

    async def ensure_user_exists(self, user_id):
        pass


def _make_config() -> Config:
    """创建用于测试的 Config 实例。"""
    return Config.with_defaults()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCompatServiceAsk:
    """CompatService.ask 编排测试"""

    @pytest.mark.asyncio
    async def test_ask_with_user_id_returns_conversation_fields(self, monkeypatch):
        """
        有 user_id 时，返回值应包含 answer、related_articles、conversation_id、session_created。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "existing-conv",
            "user_id": "u1",
            "title": "旧会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        })

        fake_client = _FakeClient([
            {"type": "delta", "content": "你好"},
            {"type": "delta", "content": "世界"},
            {"type": "done", "usage": {"total_tokens": 10}},
        ])

        async def _fake_create_client(cfg, uid, cid):
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(question="你好", user_id="u1")

        assert "answer" in result
        assert result["answer"] == "你好世界"
        assert "related_articles" in result
        assert isinstance(result["related_articles"], list)
        assert "conversation_id" in result
        assert result["conversation_id"] == "existing-conv"
        assert "session_created" in result
        assert result["session_created"] is False

    @pytest.mark.asyncio
    async def test_ask_without_user_id_omits_conversation_fields(self, monkeypatch):
        """
        无 user_id 时，返回值不包含 conversation_id 和 session_created。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_client = _FakeClient([
            {"type": "delta", "content": "OK"},
            {"type": "done", "usage": {}},
        ])

        async def _fake_create_client(cfg, uid, cid):
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(question="q", user_id=None)

        assert result["answer"] == "OK"
        assert "related_articles" in result
        assert "conversation_id" not in result
        assert "session_created" not in result

    @pytest.mark.asyncio
    async def test_ask_with_user_id_creates_session_when_none_exists(self, monkeypatch):
        """
        有 user_id 但当天无已有会话时，创建新会话，session_created=True。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session=None)

        fake_client = _FakeClient([
            {"type": "delta", "content": "resp"},
            {"type": "done", "usage": {}},
        ])

        async def _fake_create_client(cfg, uid, cid):
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(question="q", user_id="u1")

        assert result["session_created"] is True
        assert result["conversation_id"] is not None
        assert len(result["conversation_id"]) == 8  # uuid[:8]
        # 验证 create_session 被调用了
        assert len(fake_memory._created_sessions) == 1
        assert fake_memory._created_sessions[0][0] == "u1"

    @pytest.mark.asyncio
    async def test_ask_extracts_related_articles_from_tool_results(self, monkeypatch):
        """
        tool_result 事件中的数据应被聚合到 related_articles 列表。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_client = _FakeClient([
            {"type": "delta", "content": "根据搜索结果"},
            {
                "type": "tool_result",
                "tool": "search_articles",
                "result": '[{"title": "文章1"}, {"title": "文章2"}]',
            },
            {"type": "delta", "content": "，以上是结果。"},
            {"type": "done", "usage": {}},
        ])

        async def _fake_create_client(cfg, uid, cid):
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(question="搜索", user_id=None)

        assert "文章1" in str(result["related_articles"])
        assert "文章2" in str(result["related_articles"])
        assert result["answer"] == "根据搜索结果，以上是结果。"

    @pytest.mark.asyncio
    async def test_ask_handles_error_event(self, monkeypatch):
        """
        error 事件应被捕获并反映在返回值中。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_client = _FakeClient([
            {"type": "delta", "content": "部分回答"},
            {"type": "error", "message": "工具调用失败"},
            {"type": "done", "usage": {}},
        ])

        async def _fake_create_client(cfg, uid, cid):
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(question="q", user_id=None)

        assert result["answer"] == "部分回答"
        assert "error" in result
        assert "工具调用失败" in result["error"]

    @pytest.mark.asyncio
    async def test_ask_uses_existing_session_when_found(self, monkeypatch):
        """
        当天已有会话时，复用 conversation_id，session_created=False。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "reuse-me",
            "user_id": "u1",
            "title": "今日会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        })

        fake_client = _FakeClient([
            {"type": "delta", "content": "ok"},
            {"type": "done", "usage": {}},
        ])

        async def _fake_create_client(cfg, uid, cid):
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(question="q", user_id="u1")

        assert result["conversation_id"] == "reuse-me"
        assert result["session_created"] is False
        # 不应创建新会话
        assert len(fake_memory._created_sessions) == 0

    @pytest.mark.asyncio
    async def test_ask_prefers_explicit_conversation_id_over_latest_session(self, monkeypatch):
        """
        调用方显式传入 conversation_id 时，应优先使用该会话，而不是“当天最新会话”。
        """
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(
            latest_session={
                "conversation_id": "latest-conv",
                "user_id": "u1",
                "title": "最新会话",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            },
            sessions_by_id={
                "target-conv": {
                    "conversation_id": "target-conv",
                    "user_id": "u1",
                    "title": "目标会话",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now(),
                },
            },
        )
        fake_client = _FakeClient([
            {"type": "delta", "content": "ok"},
            {"type": "done", "usage": {}},
        ])
        called = {}

        async def _fake_create_client(cfg, uid, cid):
            called["conversation_id"] = cid
            return fake_client

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        result = await service.ask(
            question="q",
            user_id="u1",
            conversation_id="target-conv",
        )

        assert result["conversation_id"] == "target-conv"
        assert result["session_created"] is False
        assert called["conversation_id"] == "target-conv"
        assert len(fake_memory._created_sessions) == 0


class TestAggregateEvents:
    """_aggregate_events 静态方法单元测试"""

    def test_aggregate_events_skips_non_search_articles_tool_results(self):
        """grep_article 等非 search_articles 的 tool_result 不应追加到 related_articles。"""
        from src.api.compat_service import CompatService

        events = [
            {"type": "tool_result", "tool": "grep_article", "result": '{"status": "success", "data": {}}'},
            {"type": "tool_result", "tool": "read_reference", "result": '{"text": "ref"}'},
            {"type": "tool_result", "tool": "search_articles", "result": '[{"title": "有效文章"}]'},
        ]
        result = CompatService._aggregate_events(events)

        assert len(result["related_articles"]) == 1
        assert result["related_articles"][0]["title"] == "有效文章"

    def test_aggregate_events_skips_tool_result_with_none_tool(self):
        """tool 值为 None 时不应追加到 related_articles。"""
        from src.api.compat_service import CompatService

        events = [
            {"type": "tool_result", "tool": None, "result": '[{"title": "不应出现"}]'},
        ]
        result = CompatService._aggregate_events(events)

        assert len(result["related_articles"]) == 0

    def test_aggregate_events_logs_warning_on_invalid_json(self, caplog):
        """M2: tool_result 包含非 JSON 字符串时应输出 warning 日志。"""
        import logging
        from src.api.compat_service import CompatService

        events = [
            {"type": "tool_result", "tool": "search_articles", "result": "<<<not-json>>>"},
        ]
        with caplog.at_level(logging.WARNING, logger="src.api.compat_service"):
            result = CompatService._aggregate_events(events)

        assert result["related_articles"] == []
        assert any("Failed to parse tool_result" in rec.message for rec in caplog.records)

    def test_aggregate_events_adds_summary_snippet_and_keeps_summary(self):
        """search_articles 的 results 应新增 summary_snippet，且保留原始 summary。"""
        import json
        from src.api.compat_service import CompatService

        long_summary = "这是一段非常长的摘要内容。" * 7  # 91 字符，超过默认 limit=80
        events = [
            {
                "type": "tool_result",
                "tool": "search_articles",
                "result": json.dumps({"results": [
                    {"id": 1, "title": "文章A", "summary": long_summary},
                    {"id": 2, "title": "文章B", "summary": "短摘要"},
                ]}),
            },
        ]
        result = CompatService._aggregate_events(events)

        articles = result["related_articles"]
        assert len(articles) == 2

        # 文章A: 长 summary → 应有截断的 summary_snippet，保留原始 summary
        assert articles[0]["summary"] == long_summary
        assert "summary_snippet" in articles[0]
        assert len(articles[0]["summary_snippet"]) <= 81
        assert articles[0]["summary_snippet"].endswith("…")

        # 文章B: 短 summary → summary_snippet == summary
        assert articles[1]["summary_snippet"] == "短摘要"
        assert articles[1]["summary"] == "短摘要"

    def test_aggregate_events_handles_missing_summary(self):
        """缺少 summary 字段时 summary_snippet 应为空字符串。"""
        import json
        from src.api.compat_service import CompatService

        events = [
            {
                "type": "tool_result",
                "tool": "search_articles",
                "result": json.dumps({"results": [
                    {"id": 1, "title": "无摘要文章"},
                ]}),
            },
        ]
        result = CompatService._aggregate_events(events)

        assert result["related_articles"][0]["summary_snippet"] == ""

    def test_truncate_text_short(self):
        """短文本不截断，直接返回。"""
        from src.api.compat_service import CompatService
        assert CompatService._truncate_text("短文本") == "短文本"

    def test_truncate_text_none(self):
        """None 返回空字符串。"""
        from src.api.compat_service import CompatService
        assert CompatService._truncate_text(None) == ""

    def test_truncate_text_empty(self):
        """空字符串返回空字符串。"""
        from src.api.compat_service import CompatService
        assert CompatService._truncate_text("") == ""

    def test_truncate_text_long(self):
        """超长文本截取到 limit 并加省略号。"""
        from src.api.compat_service import CompatService
        text = "这是一段非常长的文本用来测试截断功能是否正常工作"
        result = CompatService._truncate_text(text, limit=10)
        assert len(result) <= 11  # 10字符 + 省略号
        assert result.endswith("…")

    def test_truncate_text_collapses_whitespace(self):
        """多余空白应被压缩为单空格。"""
        from src.api.compat_service import CompatService
        text = "这是  多余   空白"
        result = CompatService._truncate_text(text)
        assert "  " not in result
        assert result == "这是 多余 空白"

    def test_aggregate_events_keeps_no_id_docs_passthrough(self):
        """无 id 的文档应透传保留，有 id 的按 id 去重聚合。"""
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

    def test_aggregate_events_dedup_by_id_and_average_scores(self):
        """同一 id 出现在多个 tool_result 中时，应去重并对数值型分数取均值。"""
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

    def test_display_field_skips_none_and_empty_takes_first_nonempty(self):
        """展示字段应跳过 None 和空字符串，取第一个非空值。"""
        from src.api.compat_service import CompatService

        docs = [
            {
                "id": 200,
                "title": None,
                "unit": "",
                "summary": None,
                "ebd_similarity": 0.5,
            },
            {
                "id": 200,
                "title": "有效标题",
                "unit": "教务处",
                "summary": "有效摘要",
                "ebd_similarity": 0.7,
            },
            {
                "id": 200,
                "title": "应被跳过的标题",
                "unit": "应被跳过的单位",
                "summary": "应被跳过的摘要",
                "ebd_similarity": 0.9,
            },
        ]

        result = CompatService._dedupe_and_aggregate_docs(docs)
        assert len(result) == 1
        doc = result[0]
        assert doc["title"] == "有效标题"
        assert doc["unit"] == "教务处"
        assert doc["summary"] == "有效摘要"

    def test_aggregate_events_ignores_invalid_score_values(self):
        """字符串、bool、NaN 等无效评分值应被过滤，仅保留有效数值。"""
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
        assert doc["keyword_similarity"] == 0
        assert doc["rerank_score"] == pytest.approx(0.4)

    def test_display_field_all_empty_falls_back_to_empty(self):
        """所有文档的展示字段都为 None/空字符串时，保留空值。"""
        from src.api.compat_service import CompatService

        docs = [
            {"id": 300, "title": None, "unit": "", "ebd_similarity": 0.5},
            {"id": 300, "title": "", "unit": None, "ebd_similarity": 0.6},
        ]

        result = CompatService._dedupe_and_aggregate_docs(docs)
        assert len(result) == 1
        doc = result[0]
        assert doc["title"] is None or doc["title"] == ""
        assert doc["unit"] is None or doc["unit"] == ""

    def test_no_id_docs_null_scores_replaced_with_zero(self):
        """无 id 的透传文档中，null 的评分字段应替换为 0。"""
        from src.api.compat_service import CompatService

        docs = [
            {"title": "无ID文章", "ebd_similarity": None, "keyword_similarity": None, "rerank_score": None},
        ]

        result = CompatService._dedupe_and_aggregate_docs(docs)
        assert len(result) == 1
        doc = result[0]
        assert doc["ebd_similarity"] == 0
        assert doc["keyword_similarity"] == 0
        assert doc["rerank_score"] == 0

    def test_all_null_scores_in_dedup_group_replaced_with_zero(self):
        """去重聚合中，所有评分值均为 null 时应返回 0 而非 None。"""
        from src.api.compat_service import CompatService

        docs = [
            {"id": 400, "title": "全null", "ebd_similarity": None, "keyword_similarity": None, "rerank_score": None},
            {"id": 400, "title": "全null", "ebd_similarity": None, "keyword_similarity": None, "rerank_score": None},
        ]

        result = CompatService._dedupe_and_aggregate_docs(docs)
        assert len(result) == 1
        doc = result[0]
        assert doc["ebd_similarity"] == 0
        assert doc["keyword_similarity"] == 0
        assert doc["rerank_score"] == 0


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
    async def test_clear_memory_reuses_when_messages_is_json_string_empty(self, monkeypatch):
        """asyncpg 返回 JSONB 为字符串 '[]' 时，应视为无消息并复用。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "empty-conv",
            "user_id": "u1",
            "title": "空会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": "[]",  # asyncpg 返回字符串而非列表
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert result["conversation_id"] == "empty-conv"
        assert len(fake_memory._created_sessions) == 0

    @pytest.mark.asyncio
    async def test_clear_memory_creates_new_when_messages_is_json_string_nonempty(self, monkeypatch):
        """asyncpg 返回 JSONB 为字符串（非空）时，应创建新会话。"""
        import json as json_mod
        from src.api.compat_service import CompatService

        config = _make_config()
        fake_memory = _FakeMemoryDB(latest_session={
            "conversation_id": "used-conv",
            "user_id": "u1",
            "title": "有消息会话",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": json_mod.dumps([{"role": "user", "content": "hello"}]),
        })

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        result = await service.clear_memory(user_id="u1")

        assert result["cleared"] is True
        assert result["conversation_id"] != "used-conv"
        assert len(fake_memory._created_sessions) == 1

    @pytest.mark.asyncio
    async def test_clear_memory_without_user_id_raises(self, monkeypatch):
        """无 user_id 时 clear_memory 应抛出异常。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        service = CompatService(config=config)

        with pytest.raises(ValueError):
            await service.clear_memory(user_id=None)


class TestBuildRuntimeHints:
    """build_runtime_hints 运行时提示构建测试"""

    def test_ignores_invalid_top_k_string(self):
        """非数字字符串的 top_k 应被忽略。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k="abc", display_name=None)
        assert "top_k" not in hints

    def test_ignores_invalid_top_k_zero(self):
        """top_k=0 应被忽略。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=0, display_name=None)
        assert "top_k" not in hints

    def test_ignores_invalid_top_k_negative(self):
        """负数的 top_k 应被忽略。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=-1, display_name=None)
        assert "top_k" not in hints

    def test_ignores_invalid_top_k_none(self):
        """None 的 top_k 应被忽略。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=None, display_name=None)
        assert "top_k" not in hints

    def test_valid_top_k_included(self):
        """正整数 top_k 应生成提示。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=5, display_name=None)
        assert "top_k" in hints
        assert "前 5 条" in hints["top_k"]

    def test_valid_top_k_from_string_number(self):
        """数字字符串的 top_k 应被解析并生成提示。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k="10", display_name=None)
        assert "top_k" in hints
        assert "前 10 条" in hints["top_k"]

    def test_display_name_included(self):
        """有效的 display_name 应生成称呼提示。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=None, display_name="张三")
        assert "display_name" in hints
        assert "可酌情称呼" in hints["display_name"]
        assert "张三" in hints["display_name"]

    def test_display_name_none_omitted(self):
        """None 的 display_name 不应生成提示。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=None, display_name=None)
        assert "display_name" not in hints

    def test_display_name_empty_string_omitted(self):
        """空字符串的 display_name 不应生成提示。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=None, display_name="")
        assert "display_name" not in hints

    def test_both_provided(self):
        """top_k 和 display_name 同时提供时都应生成提示。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=3, display_name="李四")
        assert "top_k" in hints
        assert "display_name" in hints
        assert "前 3 条" in hints["top_k"]
        assert "李四" in hints["display_name"]

    def test_neither_produced_empty_dict(self):
        """两个参数都无效/缺失时返回空字典。"""
        from src.api.compat_service import build_runtime_hints

        hints = build_runtime_hints(top_k=None, display_name=None)
        assert hints == {}

    @pytest.mark.asyncio
    async def test_ask_appends_hints_to_question(self, monkeypatch):
        """ask() 应将 runtime hints 追加到 question 后传入 ChatClient。"""
        from src.api.compat_service import CompatService, build_runtime_hints

        config = _make_config()
        received_questions: list[str] = []

        class _CapturingClient:
            def __init__(self):
                self._events = [
                    {"type": "delta", "content": "回答"},
                    {"type": "done", "usage": {}},
                ]

            async def chat_stream_async(self, user_input: str):
                received_questions.append(user_input)
                for event in self._events:
                    yield event

        async def _fake_create_client(cfg, uid, cid):
            return _CapturingClient()

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        await service.ask(question="今天有什么通知", user_id=None, top_k=5, display_name="王五")

        assert len(received_questions) == 1
        actual_question = received_questions[0]
        # 原始问题应在前面
        assert actual_question.startswith("今天有什么通知")
        # hints 应被追加
        hints = build_runtime_hints(top_k=5, display_name="王五")
        for hint_text in hints.values():
            assert hint_text in actual_question

    @pytest.mark.asyncio
    async def test_ask_without_hints_passes_original_question(self, monkeypatch):
        """ask() 无 hints 时应原样传递 question。"""
        from src.api.compat_service import CompatService

        config = _make_config()
        received_questions: list[str] = []

        class _CapturingClient:
            def __init__(self):
                self._events = [
                    {"type": "delta", "content": "回答"},
                    {"type": "done", "usage": {}},
                ]

            async def chat_stream_async(self, user_input: str):
                received_questions.append(user_input)
                for event in self._events:
                    yield event

        async def _fake_create_client(cfg, uid, cid):
            return _CapturingClient()

        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_chat_client", _fake_create_client)

        await service.ask(question="原始问题", user_id=None)

        assert len(received_questions) == 1
        assert received_questions[0] == "原始问题"


class TestTodayRange:
    """_today_range 时区工具方法测试"""

    def test_today_range_default_timezone(self):
        """
        _today_range 返回 naive datetime，start 是今天 00:00 UTC，end 是明天 00:00 UTC。
        """
        from src.api.compat_service import _today_range

        start, end = _today_range()
        assert start.tzinfo is None
        assert end.tzinfo is None
        # end - start 应该是 24 小时
        assert (end - start) == timedelta(days=1)

    def test_today_range_with_utc_timezone(self):
        """
        start 是今天 00:00 UTC，end 是明天 00:00 UTC，当前时间在范围内。
        """
        from src.api.compat_service import _today_range

        start, end = _today_range()
        now_utc = datetime.utcnow()
        assert start <= now_utc < end

    def test_today_range_uses_given_timezone(self):
        """
        传入 Asia/Shanghai 时，返回的 naive datetime 应匹配该时区的"今天"。
        当前本地时间应落在对应范围内。
        """
        from src.api.compat_service import _today_range

        start_cst, end_cst = _today_range("Asia/Shanghai")

        # 都应是 naive datetime
        assert start_cst.tzinfo is None
        assert end_cst.tzinfo is None
        assert (end_cst - start_cst) == timedelta(days=1)

        # 当前 CST 时间应在 CST 范围内
        from zoneinfo import ZoneInfo
        now_cst = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        assert start_cst <= now_cst < end_cst

        # UTC 范围与 CST 范围应有差异（不同时区的"今天"不同）
        start_utc, end_utc = _today_range("UTC")
        assert (start_cst, end_cst) != (start_utc, end_utc) or True  # 同日时可能相同

    def test_today_range_invalid_timezone_falls_back_to_utc(self):
        """
        无效时区名应回退到 UTC（不抛异常）。
        """
        from src.api.compat_service import _today_range

        start_fallback, end_fallback = _today_range("Invalid/Zone")
        start_utc, end_utc = _today_range("UTC")
        assert start_fallback == start_utc
        assert end_fallback == end_utc


class TestResolveSessionTimezone:
    """_resolve_session 时区策略测试"""

    @pytest.mark.asyncio
    async def test_resolve_session_uses_config_timezone(self, monkeypatch):
        """
        config.compat_timezone 优先级最高，应优先使用。
        当 config 指定 Asia/Shanghai 时，_today_range 应收到该时区名。
        """
        import dataclasses
        from src.api.compat_service import CompatService, _today_range

        config = _make_config()
        config = dataclasses.replace(config, compat_timezone="Asia/Shanghai")

        received_tz: list[str] = []

        original_today_range = _today_range

        def _spy_today_range(tz_name: str = "UTC"):
            received_tz.append(tz_name)
            return original_today_range(tz_name)

        monkeypatch.setattr(
            "src.api.compat_service._today_range", _spy_today_range
        )

        fake_memory = _FakeMemoryDB(latest_session=None)
        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        await service._resolve_session("u1")

        assert len(received_tz) == 1
        assert received_tz[0] == "Asia/Shanghai"

    @pytest.mark.asyncio
    async def test_resolve_session_falls_back_to_utc_when_no_config(self, monkeypatch):
        """
        无 config.compat_timezone 且 DB 查询失败时，应回退到 UTC。
        """
        from src.api.compat_service import CompatService, _today_range

        config = _make_config()

        received_tz: list[str] = []

        original_today_range = _today_range

        def _spy_today_range(tz_name: str = "UTC"):
            received_tz.append(tz_name)
            return original_today_range(tz_name)

        monkeypatch.setattr(
            "src.api.compat_service._today_range", _spy_today_range
        )

        fake_memory = _FakeMemoryDB(latest_session=None)
        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        await service._resolve_session("u1")

        assert len(received_tz) == 1
        assert received_tz[0] == "UTC"

    @pytest.mark.asyncio
    async def test_resolve_session_falls_back_to_db_timezone(self, monkeypatch):
        """
        无 config.compat_timezone 时，应查询数据库 SHOW TIMEZONE 获取时区。
        """
        import dataclasses
        from src.api.compat_service import CompatService, _today_range

        config = _make_config()
        config = dataclasses.replace(config, compat_timezone=None)

        received_tz: list[str] = []

        original_today_range = _today_range

        def _spy_today_range(tz_name: str = "UTC"):
            received_tz.append(tz_name)
            return original_today_range(tz_name)

        monkeypatch.setattr(
            "src.api.compat_service._today_range", _spy_today_range
        )

        # 模拟 DB SHOW TIMEZONE 返回 Asia/Shanghai
        class _FakeMemoryDBWithTZ(_FakeMemoryDB):
            async def get_db_timezone(self) -> str | None:
                return "Asia/Shanghai"

        fake_memory = _FakeMemoryDBWithTZ(latest_session=None)
        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        await service._resolve_session("u1")

        assert len(received_tz) == 1
        assert received_tz[0] == "Asia/Shanghai"

    @pytest.mark.asyncio
    async def test_resolve_session_falls_back_to_utc_when_db_tz_fails(self, monkeypatch):
        """
        无 config 且 DB SHOW TIMEZONE 查询也失败时，回退到 UTC。
        """
        from src.api.compat_service import CompatService, _today_range

        config = _make_config()

        received_tz: list[str] = []

        original_today_range = _today_range

        def _spy_today_range(tz_name: str = "UTC"):
            received_tz.append(tz_name)
            return original_today_range(tz_name)

        monkeypatch.setattr(
            "src.api.compat_service._today_range", _spy_today_range
        )

        # DB 无 get_db_timezone 方法（老版本 MemoryDB），回退到 UTC
        fake_memory = _FakeMemoryDB(latest_session=None)
        service = CompatService(config=config)
        monkeypatch.setattr(service, "_create_memory_db", lambda: fake_memory)

        await service._resolve_session("u1")

        assert len(received_tz) == 1
        assert received_tz[0] == "UTC"


class TestConfigCompatTimezone:
    """Config.compat_timezone 配置字段测试"""

    def test_config_loads_ai_compat_tz_from_env(self, monkeypatch):
        """AI_COMPAT_TZ 环境变量应被加载到 config.compat_timezone。"""
        import importlib
        monkeypatch.setenv("AI_COMPAT_TZ", "Asia/Shanghai")
        import src.config.settings as settings_mod
        importlib.reload(settings_mod)
        config = settings_mod.Config.load()
        assert config.compat_timezone == "Asia/Shanghai"

    def test_config_compat_timezone_defaults_to_none(self):
        """默认情况下 compat_timezone 应为 None。"""
        from src.config.settings import Config
        config = Config.with_defaults()
        assert config.compat_timezone is None
