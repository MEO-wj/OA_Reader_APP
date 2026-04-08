"""Summarizer 主力/兜底策略单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from crawler.services.ai_load_balancer import ModelConfig, PrimaryFallbackBalancer


def _make_config(prefix: str = "primary") -> ModelConfig:
    return ModelConfig(
        api_key=f"sk-{prefix}",
        base_url=f"http://{prefix}/v1/chat/completions",
        model=f"{prefix}-model",
    )


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {
        "choices": [{"message": {"content": "这是摘要"}}]
    }
    return resp


def _make_balancer():
    return PrimaryFallbackBalancer(
        primary=_make_config("primary"),
        fallback=_make_config("fallback"),
    )


class TestSummarizerFallback:
    """主力/兜底切换逻辑测试。"""

    def test_primary_success_returns_immediately(self):
        """主力模型成功时直接返回，不调用兜底。"""
        balancer = _make_balancer()

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", return_value=_mock_response()) as mock_post:
            from crawler.summarizer import Summarizer
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_count == 1
        assert mock_post.call_args[0][0] == "http://primary/v1/chat/completions"

    def test_primary_fails_uses_fallback(self):
        """主力模型失败时切换到兜底模型。"""
        balancer = _make_balancer()
        fail_resp = _mock_response(status_code=500, json_data={"error": "internal"})
        success_resp = _mock_response(status_code=200)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", side_effect=[fail_resp, success_resp]) as mock_post:
            from crawler.summarizer import Summarizer
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_count == 2
        second_url = mock_post.call_args_list[1][0][0]
        assert second_url == "http://fallback/v1/chat/completions"

    def test_both_fail_returns_none(self):
        """主力 + 兜底都失败时返回 None。"""
        balancer = _make_balancer()
        fail_resp = _mock_response(status_code=500, json_data={"error": "internal"})

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", return_value=fail_resp):
            from crawler.summarizer import Summarizer
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result is None

    def test_primary_429_triggers_fallback(self):
        """主力模型 429 时标记冷却并切换到兜底。"""
        balancer = _make_balancer()
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.json.return_value = {}
        success_resp = _mock_response(status_code=200)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", side_effect=[resp_429, success_resp]):
            from crawler.summarizer import Summarizer
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert not balancer.primary.is_available  # 被标记了 429 冷却

    def test_no_balancer_uses_single_config(self):
        """无 balancer 时走单模型配置（向后兼容）。"""
        config = MagicMock()
        config.ai_provider_mode = "single"
        config.api_key = "sk-single"
        config.ai_base_url = "http://single/v1/chat/completions"
        config.ai_model = "single-model"

        with patch("crawler.summarizer._get_load_balancer", return_value=None), \
             patch("crawler.summarizer.http_post", return_value=_mock_response()) as mock_post:
            from crawler.summarizer import Summarizer
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = config
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_args[0][0] == "http://single/v1/chat/completions"

    def test_primary_network_error_uses_fallback(self):
        """主力网络错误（http_post 返回 None）时切兜底。"""
        balancer = _make_balancer()
        success_resp = _mock_response(status_code=200)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", side_effect=[None, success_resp]) as mock_post:
            from crawler.summarizer import Summarizer
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_count == 2


class TestExtractSummary:
    """摘要文本清洗测试。"""

    def test_extract_summary_strips_think_blocks(self):
        """兼容模型输出 <think> 块时，不应写入最终摘要。"""
        from crawler.summarizer import _extract_summary

        resp = _mock_response(
            json_data={
                "choices": [
                    {
                        "message": {
                            "content": "<think>先分析通知重点</think>\n最终摘要内容"
                        }
                    }
                ]
            }
        )

        assert _extract_summary(resp) == "最终摘要内容"
