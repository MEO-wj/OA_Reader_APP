"""app.py 工具函数测试。"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestMaskApiKey:
    """API Key 掩码测试。"""

    def test_normal_key(self):
        """测试正常长度 Key。"""
        from ai_end import app as app_module

        # 超过12个字符才掩码
        result = app_module._mask_api_key("sk-test-1234567890")
        # 返回 "sk-test-" 的前8位 + "..." + 最后4位
        assert result == "sk-test-...7890"

    def test_short_key(self):
        """测试短 Key。"""
        from ai_end import app as app_module

        # 12个字符或更少返回 ***
        result = app_module._mask_api_key("sk-short")
        assert result == "***"

    def test_exact_12_char_key(self):
        """测试恰好 12 字符的 Key。"""
        from ai_end import app as app_module

        # 12字符时不掩码
        result = app_module._mask_api_key("123456789012")
        assert result == "***"  # 实际行为是 <= 12 返回 ***

    def test_empty_key(self):
        """测试空 Key。"""
        from ai_end import app as app_module

        result = app_module._mask_api_key("")
        assert result == "***"


class TestNormalizeAiBaseUrl:
    """AI Base URL 规范化测试。"""

    def test_normal_url(self):
        """测试正常 URL。"""
        from ai_end import app as app_module

        result = app_module._normalize_ai_base_url("https://api.example.com/v1")
        assert result == "https://api.example.com/v1"

    def test_url_with_chat_completions(self):
        """测试带 /chat/completions 的 URL。"""
        from ai_end import app as app_module

        result = app_module._normalize_ai_base_url("https://api.example.com/v1/chat/completions")
        assert result == "https://api.example.com/v1"

    def test_url_with_v1_chat_completions(self):
        """测试带 /v1/chat/completions 的 URL。"""
        from ai_end import app as app_module

        result = app_module._normalize_ai_base_url("https://api.example.com/v1/chat/completions")
        assert result == "https://api.example.com/v1"

    def test_trailing_slash(self):
        """测试尾随斜杠。"""
        from ai_end import app as app_module

        result = app_module._normalize_ai_base_url("https://api.example.com/v1/")
        assert result == "https://api.example.com/v1"

    def test_none_url(self):
        """测试 None URL。"""
        from ai_end import app as app_module

        result = app_module._normalize_ai_base_url(None)
        assert result is None


class TestTruncateText:
    """文本截断测试。"""

    def test_normal_text(self):
        """测试正常文本。"""
        from ai_end import app as app_module

        result = app_module._truncate_text("hello world")
        assert result == "hello world"

    def test_text_over_limit(self):
        """测试超过限制的文本。"""
        from ai_end import app as app_module

        text = "a" * 100
        result = app_module._truncate_text(text, limit=50)

        # 50 + 省略号(1) = 51
        assert len(result) == 51
        assert result.endswith("…")

    def test_exact_limit(self):
        """测试恰好达到限制。"""
        from ai_end import app as app_module

        text = "a" * 80
        result = app_module._truncate_text(text, limit=80)

        assert result == text

    def test_none_text(self):
        """测试 None 文本。"""
        from ai_end import app as app_module

        result = app_module._truncate_text(None)
        assert result == ""

    def test_whitespace_normalization(self):
        """测试空白字符规范化。"""
        from ai_end import app as app_module

        text = "hello    world  \n  test"
        result = app_module._truncate_text(text)

        assert result == "hello world test"


class TestSerializeValue:
    """值序列化测试。"""

    def test_serialize_datetime(self):
        """测试 datetime 序列化。"""
        from ai_end import app as app_module

        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = app_module._serialize_value(dt)

        assert result == "2024-01-15T10:30:00"

    def test_serialize_date(self):
        """测试 date 序列化。"""
        from ai_end import app as app_module

        d = date(2024, 1, 15)
        result = app_module._serialize_value(d)

        assert result == "2024-01-15"

    def test_serialize_list(self):
        """测试列表序列化。"""
        from ai_end import app as app_module

        lst = [1, 2, 3]
        result = app_module._serialize_value(lst)

        assert result == [1, 2, 3]

    def test_serialize_nested_list(self):
        """测试嵌套列表序列化。"""
        from ai_end import app as app_module

        lst = [datetime(2024, 1, 1), date(2024, 1, 2)]
        result = app_module._serialize_value(lst)

        assert result == ["2024-01-01T00:00:00", "2024-01-02"]

    def test_serialize_dict(self):
        """测试字典序列化。"""
        from ai_end import app as app_module

        d = {"key": "value", "num": 123}
        result = app_module._serialize_value(d)

        assert result == {"key": "value", "num": 123}

    def test_serialize_nested_dict(self):
        """测试嵌套字典序列化。"""
        from ai_end import app as app_module

        d = {"date": datetime(2024, 1, 1)}
        result = app_module._serialize_value(d)

        assert result == {"date": "2024-01-01T00:00:00"}

    def test_serialize_string(self):
        """测试字符串序列化。"""
        from ai_end import app as app_module

        result = app_module._serialize_value("hello")
        assert result == "hello"


class TestBuildMemoryMessages:
    """构建记忆消息测试。"""

    def test_empty_history(self):
        """测试空历史。"""
        from ai_end import app as app_module

        result = app_module._build_memory_messages([])
        assert result == []

    def test_single_message(self):
        """测试单条消息。"""
        from ai_end import app as app_module
        from langchain_core.messages import HumanMessage, AIMessage

        history = [{"user": "hello", "assistant": "hi"}]
        result = app_module._build_memory_messages(history)

        assert len(result) == 2
        assert isinstance(result[0], HumanMessage)
        assert isinstance(result[1], AIMessage)
        assert result[0].content == "hello"
        assert result[1].content == "hi"

    def test_multiple_messages(self):
        """测试多条消息。"""
        from ai_end import app as app_module
        from langchain_core.messages import HumanMessage, AIMessage

        history = [
            {"user": "q1", "assistant": "a1"},
            {"user": "q2", "assistant": "a2"},
        ]
        result = app_module._build_memory_messages(history)

        assert len(result) == 4

    def test_strips_whitespace(self):
        """测试去除空白。"""
        from ai_end import app as app_module

        history = [{"user": "  hello  ", "assistant": "  hi  "}]
        result = app_module._build_memory_messages(history)

        assert result[0].content == "hello"
        assert result[1].content == "hi"

    def test_ignores_empty(self):
        """测试忽略空值。"""
        from ai_end import app as app_module

        history = [{"user": "", "assistant": ""}]
        result = app_module._build_memory_messages(history)

        assert result == []

    def test_handles_missing_keys(self):
        """测试处理缺失的键。"""
        from ai_end import app as app_module

        history = [{}]
        result = app_module._build_memory_messages(history)

        assert result == []


class TestBuildSystemPrompt:
    """构建系统提示测试。"""

    def test_basic_prompt(self):
        """测试基本提示。"""
        from ai_end import app as app_module

        prompt = app_module._build_system_prompt(top_k_hint=3)

        assert "校内OA管理员" in prompt
        assert "top_k" in prompt
        assert "3" in prompt

    def test_prompt_with_display_name(self):
        """测试带显示名称的提示。"""
        from ai_end import app as app_module

        prompt = app_module._build_system_prompt(top_k_hint=3, display_name="张三")

        assert "张三" in prompt

    def test_prompt_without_display_name(self):
        """测试不带显示名称的提示。"""
        from ai_end import app as app_module

        prompt = app_module._build_system_prompt(top_k_hint=3, display_name=None)

        assert "当前用户的名字" not in prompt


class TestExtractAnswer:
    """提取答案测试。"""

    def test_extract_from_ai_message(self):
        """测试从 AI 消息提取。"""
        from ai_end import app as app_module
        from langchain_core.messages import AIMessage, HumanMessage

        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="hi there"),
        ]

        result = app_module._extract_answer(messages)
        assert result == "hi there"

    def test_ignores_tool_calls(self):
        """测试忽略工具调用。"""
        from ai_end import app as app_module
        from langchain_core.messages import AIMessage

        # 使用 MagicMock 创建带 tool_calls 的消息
        msg_with_tool = AIMessage(content="")
        msg_with_tool.tool_calls = [{"name": "search"}]

        messages = [
            msg_with_tool,
            AIMessage(content="final answer"),
        ]

        result = app_module._extract_answer(messages)
        assert result == "final answer"

    def test_empty_messages(self):
        """测试空消息列表。"""
        from ai_end import app as app_module

        result = app_module._extract_answer([])
        assert result == ""


class TestExtractRelatedArticles:
    """提取相关文章测试。"""

    def test_extract_from_tool_message(self):
        """测试从工具消息提取。"""
        from ai_end import app as app_module
        from langchain_core.messages import ToolMessage

        tool_content = json.dumps({
            "related_articles": [
                {"id": 1, "title": "Article 1"},
                {"id": 2, "title": "Article 2"},
            ]
        })

        messages = [ToolMessage(content=tool_content, tool_call_id="test")]

        result = app_module._extract_related_articles(messages)

        assert len(result) == 2
        assert result[0]["id"] == 1

    def test_no_tool_messages(self):
        """测试无工具消息。"""
        from ai_end import app as app_module
        from langchain_core.messages import AIMessage

        messages = [AIMessage(content="hello")]

        result = app_module._extract_related_articles(messages)
        assert result == []

    def test_invalid_json(self):
        """测试无效 JSON。"""
        from ai_end import app as app_module
        from langchain_core.messages import ToolMessage

        messages = [ToolMessage(content="invalid json", tool_call_id="test")]

        result = app_module._extract_related_articles(messages)
        assert result == []


class TestBuildRelatedArticles:
    """构建相关文章测试。"""

    def test_build_basic(self):
        """测试基本构建。"""
        from ai_end import app as app_module

        articles = [
            {
                "id": 1,
                "title": "Test",
                "unit": "Dept",
                "published_on": date(2024, 1, 1),
                "content": "content here",
                "summary": "summary here",
                "similarity": 0.9,
            }
        ]

        result = app_module._build_related_articles(articles)

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["content_snippet"] is not None
        assert result[0]["summary_snippet"] is not None


class TestIsRateLimitError:
    """速率限制错误检测测试。"""

    def test_detects_429(self):
        """测试检测 429。"""
        from ai_end import app as app_module

        assert app_module._is_rate_limit_error(Exception("429 Too Many Requests")) is True

    def test_detects_rate_limit_string(self):
        """测试检测 rate limit 字符串。"""
        from ai_end import app as app_module

        assert app_module._is_rate_limit_error(Exception("rate limit exceeded")) is True

    def test_detects_quota(self):
        """测试检测 quota。"""
        from ai_end import app as app_module

        assert app_module._is_rate_limit_error(Exception("quota exceeded")) is True

    def test_false_for_other_errors(self):
        """测试其他错误返回 False。"""
        from ai_end import app as app_module

        assert app_module._is_rate_limit_error(Exception("connection timeout")) is False


class TestIsAiConfigured:
    """AI 配置检测测试。"""

    def test_not_configured(self, monkeypatch):
        """测试未配置。"""
        import ai_end.app as app_module
        from ai_end.config import Config

        # Mock config - 设置 ai_models 为空列表
        mock_config = Mock()
        mock_config.ai_base_url = None
        mock_config.api_key = None
        mock_config.ai_model = None
        mock_config.ai_models = []  # 关键：设置为空列表
        monkeypatch.setattr("ai_end.app.config", mock_config)
        monkeypatch.setattr("ai_end.app._load_balancer", None)

        result = app_module._is_ai_configured()
        assert result is False

    def test_fully_configured(self, monkeypatch):
        """测试完全配置。"""
        import ai_end.app as app_module
        from ai_end.config import Config

        # Mock config - 设置 ai_models 为空列表
        mock_config = Mock()
        mock_config.ai_base_url = "https://api.example.com"
        mock_config.api_key = "sk-test"
        mock_config.ai_model = "gpt-3.5"
        mock_config.ai_models = []  # 关键：设置为空列表
        monkeypatch.setattr("ai_end.app.config", mock_config)
        monkeypatch.setattr("ai_end.app._load_balancer", None)

        result = app_module._is_ai_configured()
        assert result is True


class TestMemoryKey:
    """记忆键测试。"""

    def test_memory_key_format(self):
        """测试记忆键格式。"""
        from ai_end import app as app_module

        key = app_module._memory_key("user123")
        assert key == "ai:mem:user123"

    def test_memory_key_with_special_chars(self):
        """测试特殊字符。"""
        from ai_end import app as app_module

        key = app_module._memory_key("user@example.com")
        assert key == "ai:mem:user@example.com"
