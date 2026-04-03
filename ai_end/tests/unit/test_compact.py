"""
测试 src.chat.compact - 对话历史压缩功能

TDD RED 阶段：编写测试用例
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from src.chat.compact import compact_messages
from tests.prompts_test_constants import COMPACT_PROMPT_EXPECTED_PHRASES


class TestCompactMessages:
    """测试 compact_messages 函数"""

    @pytest.mark.asyncio
    async def test_compact_messages_returns_summary_format(self):
        """
        compact_messages 应返回包含结构化摘要的列表。
        返回格式：[{"role": "assistant", "content": "## 对话摘要\n...\n## 关键结论\n...\n## 待继续事项\n...\n## 用户画像\n..."}]
        """
        # 构造简单的测试消息
        test_messages = [
            {"role": "user", "content": "我想考郑州的医院"},
            {"role": "assistant", "content": "郑州大学第一附属医院是河南龙头"},
        ]

        # 模拟 LLM 响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """## 对话摘要
用户咨询郑州地区医学院校，目标为河南地区医学考研。

## 关键结论
- 郑州大学第一附属医院是河南最好的医院
- 目标地域：河南/郑州

## 待继续事项
- 需要查询郑大一附院具体招生数据

## 用户画像
- 硬性要求：地域在河南郑州
- 优先考虑：专业为临床医学
- 风险承受：接受二战"""

        mock_create = MagicMock(return_value=mock_response)

        # Patch 在使用地点，而非定义地点
        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            result, response = await compact_messages(test_messages)

            # 验证返回格式（返回类型为 tuple[list, response]）
            assert isinstance(result, list)
            assert hasattr(response, 'choices')  # response 是 LLM 响应对象
            assert len(result) == 1
            assert result[0]["role"] == "assistant"
            assert "## 对话摘要" in result[0]["content"]
            assert "## 关键结论" in result[0]["content"]
            assert "## 待继续事项" in result[0]["content"]
            assert "## 用户画像" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_compact_messages_calls_llm_with_correct_prompt(self):
        """
        compact_messages 应使用正确的 prompt 调用 LLM。
        """
        test_messages = [
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "助手回答"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## 对话摘要\n测试"

        mock_create = MagicMock(return_value=mock_response)

        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            await compact_messages(test_messages)

            # 验证 LLM 被调用
            mock_create.assert_called_once()
            call_args = mock_create.call_args

            # 验证 model 参数
            assert call_args.kwargs.get('model') is not None

            # 验证 messages 参数
            messages = call_args.kwargs.get('messages')
            assert messages is not None
            assert len(messages) == 1
            for phrase in COMPACT_PROMPT_EXPECTED_PHRASES:
                assert phrase in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_compact_messages_uses_low_temperature(self):
        """
        compact_messages 应使用低温度（0.0-0.2）生成压缩结果。
        """
        test_messages = [
            {"role": "user", "content": "测试"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## 对话摘要\n测试"

        mock_create = MagicMock(return_value=mock_response)

        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            await compact_messages(test_messages)

            call_args = mock_create.call_args
            temperature = call_args.kwargs.get('temperature')

            assert temperature is not None
            assert temperature <= 0.2

    @pytest.mark.asyncio
    async def test_compact_messages_returns_original_on_error(self):
        """
        LLM 调用失败时，compact_messages 应返回原始消息（不压缩）。
        """
        test_messages = [
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "助手回答"},
        ]

        # 模拟 LLM 调用抛出异常
        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            mock_get_client.return_value = mock_client

            result, response = await compact_messages(test_messages)

            # 应返回原始消息和 None 响应
            assert result == test_messages
            assert response is None

    @pytest.mark.asyncio
    async def test_compact_messages_empty_list(self):
        """
        空消息列表应直接返回空列表。
        """
        result, response = await compact_messages([])

        # 应返回空列表和 None 响应
        assert result == []
        assert response is None

    @pytest.mark.asyncio
    async def test_compact_messages_single_message(self):
        """
        单条消息也应该能被压缩。
        """
        test_messages = [
            {"role": "user", "content": "只有一个问题"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## 对话摘要\n用户只有一个问题"

        mock_create = MagicMock(return_value=mock_response)

        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            result, response = await compact_messages(test_messages)

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["role"] == "assistant"
            assert hasattr(response, 'choices')  # response 是 LLM 响应对象

    @pytest.mark.asyncio
    async def test_compact_messages_includes_tool_calls_results(self):
        """
        压缩应保留 tool_calls 结果中的关键发现。
        """
        test_messages = [
            {"role": "user", "content": "查询郑州大学招生数据"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "search_schools", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "郑州大学2024年临床医学招生100人，分数线350分"}
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """## 对话摘要
用户查询郑州大学招生信息。

## 关键结论
- 郑州大学2024年临床医学招生100人
- 分数线350分

## 待继续事项
- 需要更多学校数据对比

## 用户画像
- 硬性要求：地域河南
- 优先考虑：临床医学
- 风险承受：接受二战"""

        mock_create = MagicMock(return_value=mock_response)

        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            result, response = await compact_messages(test_messages)

            assert isinstance(result, list)
            assert len(result) == 1
            assert hasattr(response, 'choices')  # response 是 LLM 响应对象
            # 验证 LLM 收到包含 tool 结果的内容
            call_args = mock_create.call_args
            messages = call_args.kwargs.get('messages')
            content = messages[0]["content"]
            assert "郑州大学" in content

    @pytest.mark.asyncio
    async def test_compact_messages_max_tokens_reasonable(self):
        """
        compact_messages 应使用合理的 max_tokens（足够大以容纳完整摘要）。
        """
        test_messages = [{"role": "user", "content": "测试"}]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## 对话摘要\n测试"

        mock_create = MagicMock(return_value=mock_response)

        with patch('src.chat.compact.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = mock_create
            mock_get_client.return_value = mock_client

            await compact_messages(test_messages)

            call_args = mock_create.call_args
            max_tokens = call_args.kwargs.get('max_tokens')

            # max_tokens 应在合理范围内（500-2000）
            assert max_tokens is not None
            assert 500 <= max_tokens <= 2000


def test_compact_prompt_template_is_centralized_constant():
    """compact.COMPACT_PROMPT_TEMPLATE 应来自集中常量 prompts_runtime.COMPACT_PROMPT_TEMPLATE"""
    from src.chat.prompts_runtime import COMPACT_PROMPT_TEMPLATE
    from src.chat.compact import COMPACT_PROMPT_TEMPLATE as IN_USE

    assert IN_USE == COMPACT_PROMPT_TEMPLATE
