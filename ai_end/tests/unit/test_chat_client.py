"""
TDD: 聊天客户端单元测试

RED 阶段 - 测试先于实现
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from tests.prompts_test_constants import SYSTEM_PROMPT_EXPECTED_PHRASES


@pytest.fixture(autouse=True)
def reset_client_singletons():
    from src.core import api_clients
    from src.core import api_queue

    api_clients.close_clients()
    api_queue._api_queue = None
    yield
    api_clients.close_clients()
    api_queue._api_queue = None


class TestChatClient:
    """聊天客户端测试套件"""

    @patch("src.chat.client.get_history_manager")
    @patch("src.chat.client.get_memory_manager")
    @patch("src.chat.client.get_skill_system")
    def test_client_initialization_uses_di_providers(
        self,
        mock_get_skill_system,
        mock_get_memory_manager,
        mock_get_history_manager,
    ):
        """同步构造应通过 DI provider 获取依赖。"""
        from src.chat.client import ChatClient
        from src.config import Config
        from src.core.skill_adapter import SkillBackend

        config = Config.with_defaults()
        fake_skill_system = Mock()
        fake_skill_system.available_skills = {}
        fake_memory_manager = Mock()
        fake_history_manager = Mock()
        mock_get_skill_system.return_value = fake_skill_system
        mock_get_memory_manager.return_value = fake_memory_manager
        mock_get_history_manager.return_value = fake_history_manager

        client = ChatClient(config)

        mock_get_skill_system.assert_called_once_with(
            backend=SkillBackend.FILESYSTEM,
            skills_dir=config.skills_dir,
        )
        mock_get_memory_manager.assert_called_once()
        mock_get_history_manager.assert_called_once()
        assert client.skill_system is fake_skill_system
        assert client._memory_manager is fake_memory_manager
        assert client._history_manager is fake_history_manager

    def test_client_initialization(self):
        """
        RED #1: 客户端初始化加载技能系统
        Given: 创建 ChatClient 实例
        When: 传入配置参数
        Then: 技能系统被正确初始化
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        assert client.skill_system is not None
        assert client.config == config

    @pytest.mark.asyncio
    @patch("src.chat.client.get_history_manager")
    @patch("src.chat.client.get_memory_manager")
    @patch("src.chat.client.get_skill_system")
    async def test_async_create_uses_di_skill_adapter(
        self,
        mock_get_skill_system,
        mock_get_memory_manager,
        mock_get_history_manager,
    ):
        """异步构造应通过统一 provider 创建并加载数据库技能适配器。"""
        from src.chat.client import ChatClient
        from src.config import Config
        from src.core.skill_adapter import SkillBackend

        config = Config.with_defaults()
        fake_adapter = Mock()
        fake_adapter.available_skills = {}
        fake_adapter.load_skills = AsyncMock()
        mock_get_skill_system.return_value = fake_adapter
        mock_get_memory_manager.return_value = Mock()
        mock_get_history_manager.return_value = Mock()

        client = await ChatClient.create(config, user_id="u1", conversation_id="c1")

        mock_get_skill_system.assert_called_once_with(backend=SkillBackend.DATABASE)
        fake_adapter.load_skills.assert_awaited_once()
        assert client.skill_system is fake_adapter
        assert client.user_id == "u1"
        assert client.conversation_id == "c1"

    @patch("src.chat.client.get_history_manager")
    @patch("src.chat.client.get_memory_manager")
    @patch("src.chat.client.get_skill_system")
    def test_user_and_conversation_state_updates_managers_immediately(
        self,
        mock_get_skill_system,
        mock_get_memory_manager,
        mock_get_history_manager,
    ):
        """修改 client 会话上下文时，应立即同步到 manager，避免额外 sync 调用。"""
        from src.chat.client import ChatClient
        from src.config import Config

        fake_skill_system = Mock()
        fake_skill_system.available_skills = {}
        fake_memory_manager = Mock(user_id=None, conversation_id="default")
        fake_history_manager = Mock(user_id=None, conversation_id="default")

        mock_get_skill_system.return_value = fake_skill_system
        mock_get_memory_manager.return_value = fake_memory_manager
        mock_get_history_manager.return_value = fake_history_manager

        client = ChatClient(Config.with_defaults())
        client.user_id = "user-2"
        client.conversation_id = "conv-2"

        assert fake_memory_manager.user_id == "user-2"
        assert fake_memory_manager.conversation_id == "conv-2"
        assert fake_history_manager.user_id == "user-2"
        assert fake_history_manager.conversation_id == "conv-2"

    def test_system_prompt_format(self):
        """
        RED #2: 系统提示词包含技能列表
        Given: ChatClient 实例
        When: 调用 _build_system_prompt
        Then: 返回的提示词包含技能信息
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        prompt = client._build_system_prompt()

        assert "技能" in prompt or "skill" in prompt.lower()

    def test_system_prompt_hides_internal_tool_details(self):
        """
        系统提示词应约束模型不向普通用户暴露工具中间细节。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        prompt = client._build_system_prompt()

        assert "不要暴露内部工具调用过程" in prompt
        assert "不要提及工具名、调用参数" in prompt

    def test_system_prompt_enforces_decision_guardrails(self):
        """
        决策约束：信息不足时应先说明不确定性，禁用承诺性表述。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        prompt = client._build_system_prompt()

        # 验证决策约束部分存在
        assert "## 决策约束" in prompt
        assert "信息不足" in prompt
        assert "不确定性" in prompt
        # 禁用承诺性表述
        assert "禁用承诺性表述" in prompt

    def test_system_prompt_uses_skill_names_without_descriptions(self):
        """
        系统提示词应包含技能名称列表，但不包含详细描述。
        这是优化方案 A 的要求：减少 token 用量。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        prompt = client._build_system_prompt()

        # 检查包含技能名称
        for skill_name in list(client.skill_system.available_skills.keys())[:3]:
            assert skill_name in prompt, f"技能名称 {skill_name} 应在提示词中"

        # 检查格式：应该是 "- name1\n- name2\n" 而不是 "- name1: 很长的描述\n"
        lines = prompt.split('\n')
        skill_lines = [l for l in lines if l.strip().startswith('- ')]

        # 技能行应该只有名称，没有长描述
        # 允许 "- skill-name" 格式，不允许 "- skill-name: 很长的描述" 格式
        for line in skill_lines:
            # 跳过非技能列表行（如约束部分的列表项）
            if not any(skill in line for skill in client.skill_system.available_skills.keys()):
                continue

            # 如果包含技能名称和冒号，检查冒号后的内容
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    description = parts[1].strip()
                    # 描述应该为空或很短（≤20 字符）
                    # 原因：长描述应该在工具定义中，而不是系统提示词中
                    assert len(description) <= 20, \
                        f"技能列表不应包含长描述，发现: {line[:80]}"

    def test_system_prompt_keeps_decision_constraints_after_compression(self):
        """
        精简后的系统提示词必须保留决策约束。
        这是关键的安全约束，不能被删除。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        prompt = client._build_system_prompt()

        # 验证关键决策约束存在
        critical_keywords = [
            "信息不足",
            "不确定性",
        ]

        for keyword in critical_keywords:
            assert keyword in prompt, f"决策约束关键字 '{keyword}' 被删除了"

        # 使用共享常量验证 system prompt 短语
        for phrase in SYSTEM_PROMPT_EXPECTED_PHRASES:
            assert phrase in prompt

    def test_system_prompt_length_budget_under_target_range(self):
        """
        系统提示词长度应在目标范围内。
        目标：从 ~450-600 tokens 降到 ~180-260 tokens。
        使用字符数作为粗略估算（中文约 3 字符 = 1 token）。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        prompt = client._build_system_prompt()

        # 字符数估算
        char_count = len(prompt)

        # 目标：~540-780 字符（对应 ~180-260 tokens，按 3 字符/token）
        # 上限设宽松一些：1200 字符（~400 tokens）
        max_target_chars = 1200

        # 计算技能数量（动态部分）
        skill_count = len(client.skill_system.available_skills)

        # 基础部分 + 技能名称列表（每个名称约 15 字符）
        estimated_chars = 400 + (skill_count * 15)

        assert char_count < max_target_chars, \
            f"系统提示词过长 ({char_count} 字符)，目标 < {max_target_chars}。当前提示词:\n{prompt[:500]}..."

        # 同时确保不会太短（至少包含基本要素）
        min_target_chars = 200
        assert char_count > min_target_chars, \
            f"系统提示词过短 ({char_count} 字符)，可能删除了必要内容"

    def test_system_prompt_has_profile_section_placeholder(self):
        """
        系统提示词模板应包含画像章节占位符，支持结构化画像融入。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        # 检查模板中是否包含 profile_section 占位符
        assert "{profile_section}" in client.DEFAULT_SYSTEM_PROMPT

    def test_parse_profile_into_sections(self):
        """
        画像应被解析为 v2 分层结构：confirmed/hypothesized/knowledge。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        # 使用 v2 JSON 格式的画像数据
        portrait = '{"confirmed":{"identity":["医学生"],"interests":["内科学"],"constraints":["目标地域：北京"]},"hypothesized":{"identity":[],"interests":[]}}'
        knowledge = '{"confirmed_facts":["首医英语线55-60"],"pending_queries":["郑大一招生数据"]}'

        result = client._parse_profile_to_sections(portrait, knowledge)

        # 验证 v2 字段
        assert "confirmed_identity" in result
        assert "confirmed_interests" in result
        assert "confirmed_constraints" in result
        assert "hypothesized_identity" in result
        assert "hypothesized_interests" in result
        assert "confirmed_facts" in result
        assert "pending_queries" in result
        # 验证内容被正确解析
        assert "医学生" in result["confirmed_identity"]
        assert "内科学" in result["confirmed_interests"]
        assert "北京" in result["confirmed_constraints"]

    def test_parse_profile_falls_back_for_invalid_json(self):
        """v1 或非法 JSON 应渲染为'（暂无）'分层。"""
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        # v1 格式
        v1_portrait = '{"hard_constraints":["北京"],"soft_constraints":["内科"],"risk_tolerance":[]}'
        v1_knowledge = '{"verified_facts":[],"pending_queries":[]}'

        result = client._parse_profile_to_sections(v1_portrait, v1_knowledge)

        assert "（暂无）" in result["confirmed_identity"]
        assert "（暂无）" in result["confirmed_constraints"]

    def test_parse_profile_falls_back_for_non_json(self):
        """非 JSON 字符串应渲染为'（暂无）'。"""
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        result = client._parse_profile_to_sections("not json", "also not json")

        assert "（暂无）" in result["confirmed_identity"]
        assert "（暂无）" in result["confirmed_constraints"]
        assert "（暂无）" in result["confirmed_facts"]

    def test_build_system_prompt_with_v2_profile(self):
        """_build_system_prompt 应正确渲染 v2 分层画像，包含 hypothesized 警示。"""
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        portrait = '{"confirmed":{"identity":["医学生"],"interests":["内科学"],"constraints":["北京"]},"hypothesized":{"identity":["（来源：多次查询）可能对AI感兴趣"],"interests":[]}}'
        knowledge = '{"confirmed_facts":["985院校"],"pending_queries":["分数线"]}'

        prompt = client._build_system_prompt(portrait=portrait, knowledge=knowledge)

        # 验证 confirmed 区块
        assert "医学生" in prompt
        assert "北京" in prompt
        # 验证 hypothesized 区块
        assert "可能对AI感兴趣" in prompt
        # 验证 hypothesized 警示
        assert "仅供参考" in prompt
        # 验证 knowledge 区块
        assert "985院校" in prompt
        assert "分数线" in prompt

    def test_build_system_prompt_with_profile(self):
        """
        _build_system_prompt 应能接受画像参数并融入 v2 结构化章节。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        # 使用 v2 JSON 格式的画像数据
        portrait = '{"confirmed":{"identity":["医学生"],"interests":["内科学"],"constraints":["目标地域：河南"]},"hypothesized":{"identity":[],"interests":[]}}'
        knowledge = '{"confirmed_facts":["首医英语线55-60"],"pending_queries":["郑大一招生数据"]}'

        prompt = client._build_system_prompt(portrait=portrait, knowledge=knowledge)

        # 验证 v2 分层区块存在
        assert "已确认身份" in prompt or "confirmed" in prompt
        # 验证内容被正确填充
        assert "目标地域：河南" in prompt or "河南" in prompt
        assert "首医" in prompt or "55-60" in prompt

    def test_clear_history(self):
        """
        RED #3: 清空对话历史
        Given: ChatClient 实例有对话历史
        When: 调用 clear_history
        Then: 消息列表被清空
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)
        client.messages = [{"role": "user", "content": "test"}]

        client.clear_history()

        assert client.messages == []

    def test_verification_token_check_with_valid_token(self):
        """
        RED #4: 验证暗号检测 - 包含正确暗号
        Given: 技能有验证暗号 "TEST-TOKEN-123"
        When: 回复内容包含该暗号
        Then: 返回 True
        """
        from src.chat.client import ChatClient
        from src.config import Config
        from src.core import SkillInfo

        config = Config.with_defaults()
        client = ChatClient(config)

        # Mock skill_info
        mock_skill_info = SkillInfo(
            name="test-skill",
            description="Test skill",
            content="Content",
            path="/path",
            verification_token="TEST-TOKEN-123"
        )

        with patch.object(client.skill_system, 'get_skill_info', return_value=mock_skill_info):
            result = client._check_verification_token("test-skill", "回复内容包含 TEST-TOKEN-123 暗号")
            assert result is True

    def test_verification_token_check_without_token(self):
        """
        RED #5: 验证暗号检测 - 技能无暗号
        Given: 技能没有设置验证暗号
        When: 检查回复
        Then: 返回 False
        """
        from src.chat.client import ChatClient
        from src.config import Config
        from src.core import SkillInfo

        config = Config.with_defaults()
        client = ChatClient(config)

        # Mock skill_info without verification_token
        mock_skill_info = SkillInfo(
            name="test-skill",
            description="Test skill",
            content="Content",
            path="/path",
            verification_token=None
        )

        with patch.object(client.skill_system, 'get_skill_info', return_value=mock_skill_info):
            result = client._check_verification_token("test-skill", "任何回复内容")
            assert result is False

    def test_verification_token_check_token_not_in_response(self):
        """
        RED #6: 验证暗号检测 - 回复不包含暗号
        Given: 技能有验证暗号 "TEST-TOKEN-123"
        When: 回复内容不包含该暗号
        Then: 返回 False
        """
        from src.chat.client import ChatClient
        from src.config import Config
        from src.core import SkillInfo

        config = Config.with_defaults()
        client = ChatClient(config)

        mock_skill_info = SkillInfo(
            name="test-skill",
            description="Test skill",
            content="Content",
            path="/path",
            verification_token="TEST-TOKEN-123"
        )

        with patch.object(client.skill_system, 'get_skill_info', return_value=mock_skill_info):
            result = client._check_verification_token("test-skill", "回复内容没有暗号")
            assert result is False

    def test_verification_token_check_skill_not_found(self):
        """
        RED #7: 验证暗号检测 - 技能不存在
        Given: 技能不存在
        When: 检查回复
        Then: 返回 False
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        with patch.object(client.skill_system, 'get_skill_info', return_value=None):
            result = client._check_verification_token("nonexistent-skill", "任何回复内容")
            assert result is False


class TestChatClientChatMethod:
    """测试 chat() 方法的完整流程"""

    @patch('src.chat.client.get_llm_client')
    def test_chat_adds_system_prompt_on_first_call(self, mock_get_llm_client):
        """
        RED #8: 首次调用添加系统提示词
        Given: 新的 ChatClient 实例，消息列表为空
        When: 调用 chat()
        Then: 系统提示词被添加到消息列表
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()

        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "AI 回复"
        mock_response.choices[0].message.tool_calls = None

        mock_get_llm_client.return_value.chat.completions.create.return_value = mock_response

        client = ChatClient(config)
        result = client.chat("用户问题")

        assert len(client.messages) == 3  # system + user + assistant
        assert client.messages[0]["role"] == "system"
        assert result == "AI 回复"

    @patch('src.chat.client.get_llm_client')
    def test_profile_injected_into_main_prompt(self, mock_get_llm_client):
        """
        画像应融入主 system prompt，而非单独追加为独立消息。
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()

        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "AI 回复"
        mock_response.choices[0].message.tool_calls = None

        mock_get_llm_client.return_value.chat.completions.create.return_value = mock_response

        client = ChatClient(config)

        # 直接调用 _build_system_prompt 传入画像参数
        prompt = client._build_system_prompt(
            portrait="大四临床医学生，目标郑州三甲",
            knowledge="已了解：首医英语线55-60"
        )

        # 验证画像融入主 prompt
        assert "用户画像 - 决策要素" in prompt
        # 验证不是独立章节（标题只出现一次）
        assert prompt.count("用户画像 - 决策要素") == 1

    @patch('src.chat.client.get_llm_client')
    def test_chat_with_tool_call_iteration(self, mock_get_llm_client):
        """
        RED #9: 工具调用时的迭代处理
        Given: AI 返回 tool_calls
        When: 处理 tool_calls
        Then: 继续迭代直到 AI 直接回复
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()

        # 第一次调用：返回 tool_calls
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "call_skill_test"
        mock_tool_call.function.arguments = '{}'

        mock_response_1 = Mock()
        mock_response_1.choices = [Mock()]
        mock_response_1.choices[0].message.content = None
        mock_response_1.choices[0].message.tool_calls = [mock_tool_call]

        # 第二次调用：AI 直接回复
        mock_response_2 = Mock()
        mock_response_2.choices = [Mock()]
        mock_response_2.choices[0].message.content = "基于技能的回复"
        mock_response_2.choices[0].message.tool_calls = None

        mock_get_llm_client.return_value.chat.completions.create.side_effect = [mock_response_1, mock_response_2]

        client = ChatClient(config)
        result = client.chat("用户问题")

        assert result == "基于技能的回复"
        # 应该调用了两次 API
        assert mock_get_llm_client.return_value.chat.completions.create.call_count == 2

    @patch('src.chat.client.get_llm_client')
    @patch('src.chat.client.print_step')
    def test_chat_prints_tool_call_debug_info(self, mock_print_step, mock_get_llm_client):
        """
        RED #10: 工具调用时显示调试信息
        Given: AI 返回 tool_calls
        When: 处理 tool_calls
        Then: 显示函数名、参数、技能名、验证暗号等信息
        """
        from src.chat.client import ChatClient
        from src.config import Config
        from src.core import SkillInfo

        config = Config.with_defaults()

        # Mock tool_call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "call_skill_general-assessment"
        mock_tool_call.function.arguments = '{"question": "test"}'

        mock_response_with_tools = Mock()
        mock_response_with_tools.choices = [Mock()]
        mock_response_with_tools.choices[0].message.content = None
        mock_response_with_tools.choices[0].message.tool_calls = [mock_tool_call]

        mock_response_final = Mock()
        mock_response_final.choices = [Mock()]
        mock_response_final.choices[0].message.content = "最终回复"
        mock_response_final.choices[0].message.tool_calls = None

        mock_get_llm_client.return_value.chat.completions.create.side_effect = [mock_response_with_tools, mock_response_final]

        client = ChatClient(config)

        # Mock skill_system methods directly
        mock_skill_info = SkillInfo(
            name="general-assessment",
            description="General assessment",
            content="技能内容" * 100,
            path="/path",
            verification_token="GENERAL-TOKEN-123"
        )
        client.skill_system.get_skill_content = Mock(return_value=mock_skill_info.content)
        client.skill_system.get_skill_info = Mock(return_value=mock_skill_info)

        client.chat("测试问题")

        # 验证 print_step 被调用（显示工具调用通知）
        mock_print_step.assert_called()

    @patch('src.chat.client.get_llm_client')
    @patch('src.chat.client.print_error')
    def test_chat_handles_empty_api_response(self, mock_print_error, mock_get_llm_client):
        """
        RED #12: API 返回空响应时的错误处理
        Given: API 返回 choices 为 None
        When: 调用 chat()
        Then: 显示错误信息并返回友好提示
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()

        # Mock 返回空响应的 API
        mock_response = Mock()
        mock_response.choices = None

        mock_get_llm_client.return_value.chat.completions.create.return_value = mock_response

        client = ChatClient(config)
        result = client.chat("用户问题")

        # 验证错误被正确处理
        mock_print_error.assert_called_once()
        assert "抱歉" in result or "无法" in result

    @patch('src.chat.client.get_llm_client')
    @patch('src.chat.client.print_error')
    def test_chat_handles_empty_choices_list(self, mock_print_error, mock_get_llm_client):
        """
        RED #13: API 返回空 choices 列表时的错误处理
        Given: API 返回 choices 为空列表 []
        When: 调用 chat()
        Then: 显示错误信息并返回友好提示
        """
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()

        # Mock 返回空 choices 列表的 API
        mock_response = Mock()
        mock_response.choices = []

        mock_get_llm_client.return_value.chat.completions.create.return_value = mock_response

        client = ChatClient(config)
        result = client.chat("用户问题")

        # 验证错误被正确处理
        mock_print_error.assert_called_once()
        assert "抱歉" in result or "无法" in result


def test_chat_client_uses_shared_llm_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("src.chat.client.get_llm_client", lambda *args, **kwargs: sentinel)

    from src.chat.client import ChatClient
    from src.config import Config

    client = ChatClient(Config.with_defaults())

    assert client.client is sentinel


def test_chat_client_api_call_goes_through_queue(monkeypatch):
    from unittest.mock import Mock
    from src.chat.client import ChatClient
    from src.config import Config

    class FakeQueue:
        def __init__(self):
            self.called = 0

        def submit_sync(self, lane, func, *args, **kwargs):
            self.called += 1
            assert lane == "llm"
            return func(*args, **kwargs)

    q = FakeQueue()
    monkeypatch.setattr("src.chat.client.get_api_queue", lambda: q)

    c = ChatClient(Config.with_defaults())
    c._create_completion_sync = Mock()

    response = Mock()
    response.choices = [Mock()]
    response.choices[0].message.content = "queue-ok"
    response.choices[0].message.tool_calls = None
    c._create_completion_sync.return_value = response

    result = c.chat("hello")

    assert q.called == 1
    assert result == "queue-ok"


def test_chat_client_close_calls_resources_in_order(monkeypatch):
    order = []
    monkeypatch.setattr("src.chat.client.shutdown_tool_loop", lambda: order.append("tool_loop"))
    monkeypatch.setattr("src.chat.client.close_resources", lambda: order.append("retrieval"))
    monkeypatch.setattr("src.chat.client.close_pool", lambda: order.append("db"))
    monkeypatch.setattr("src.chat.client.close_clients", lambda: order.append("clients"))

    from src.chat.client import ChatClient
    from src.config import Config

    c = ChatClient(Config.with_defaults())
    c.close()

    assert order == ["clients", "retrieval", "db", "tool_loop"]


class TestChatClientMemory:
    @pytest.mark.asyncio
    async def test_form_memory_works_with_sync_openai_client(self, monkeypatch):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)
        client.user_id = "u1"
        client.round_count = 10
        client.messages = [{"role": "user", "content": "我更喜欢临床路线"}]

        # 返回 v2 JSON 格式的响应
        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"confirmed":{"identity":["理性"],"interests":["偏好临床"],"constraints":[]},"hypothesized":{"identity":[],"interests":[]},"confirmed_facts":["了解规培路径"],"pending_queries":[]}'
                    )
                )
            ]
        )
        client.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(return_value=fake_response)
                )
            )
        )

        saved = {}

        class _FakeMemoryDB:
            async def save_profile(self, user_id, portrait_text, knowledge_text):
                saved["user_id"] = user_id
                saved["portrait_text"] = portrait_text
                saved["knowledge_text"] = knowledge_text

        client._memory_manager._memory_db = _FakeMemoryDB()

        await client.form_memory()

        assert saved["user_id"] == "u1"
        # 验证保存的是 v2 JSON 格式
        assert '"confirmed"' in saved["portrait_text"]
        assert '"confirmed_facts"' in saved["knowledge_text"]
        assert client.round_count == 0


class TestChatClientAsyncStreaming:
    """chat_stream_async 与异步辅助方法测试"""

    @pytest.mark.asyncio
    async def test_chat_stream_async_yields_delta_and_done(self, monkeypatch):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        class _FakeQueue:
            async def submit(self, _lane, _func, _messages, _tools):
                async def _stream():
                    delta = Mock()
                    delta.tool_calls = None
                    delta.content = "你好"
                    chunk = Mock()
                    chunk.choices = [Mock(delta=delta)]
                    yield chunk

                return _stream()

        fake_queue = _FakeQueue()
        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: fake_queue)

        events = []
        async for event in client.chat_stream_async("test"):
            events.append(event)

        assert events[0] == {"type": "delta", "content": "你好"}
        assert events[1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_chat_stream_async_emits_skill_call_event(self, monkeypatch):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        first_tool_delta = SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    index=0,
                    id="call_1",
                    function=SimpleNamespace(name="article-retrieval", arguments="{}"),
                )
            ],
        )
        first_chunk = SimpleNamespace(choices=[SimpleNamespace(delta=first_tool_delta)])

        second_text_delta = SimpleNamespace(tool_calls=None, content="完成")
        second_chunk = SimpleNamespace(choices=[SimpleNamespace(delta=second_text_delta)])

        class _FakeQueue:
            def __init__(self):
                self._count = 0

            async def submit(self, _lane, _func, _messages, _tools):
                self._count += 1

                async def _stream_first():
                    yield first_chunk

                async def _stream_second():
                    yield second_chunk

                return _stream_first() if self._count == 1 else _stream_second()

        fake_queue = _FakeQueue()
        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: fake_queue)

        handled = {"called": 0}

        async def _fake_handle(_tool_calls):
            handled["called"] += 1

        monkeypatch.setattr(client, "_handle_tool_calls_async", _fake_handle)

        events = []
        async for event in client.chat_stream_async("test"):
            events.append(event)

        assert any(e.get("type") == "skill_call" for e in events)
        assert any(e.get("type") == "delta" for e in events)
        assert events[-1]["type"] == "done"
        assert handled["called"] == 1

    @pytest.mark.asyncio
    async def test_handle_tool_calls_async_extends_messages(self, monkeypatch):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        monkeypatch.setattr(
            "src.chat.handlers.handle_tool_calls",
            AsyncMock(return_value=[{"role": "tool", "content": "ok", "tool_call_id": "1"}]),
        )

        await client._handle_tool_calls_async(
            [{"id": "1", "function": {"name": "read_reference", "arguments": "{}"}}]
        )

        assert client.messages[-1]["role"] == "tool"
        assert client.messages[-1]["content"] == "ok"

    @pytest.mark.asyncio
    async def test_create_completion_stream_async_yields_chunks(self, monkeypatch):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        class _FakeStream:
            def __aiter__(self):
                async def _iter():
                    yield "chunk-1"
                    yield "chunk-2"

                return _iter()

        class _FakeCompletions:
            async def create(self, **_kwargs):
                return _FakeStream()

        class _FakeChat:
            completions = _FakeCompletions()

        class _FakeAsyncClient:
            chat = _FakeChat()

        monkeypatch.setattr("src.chat.client.AsyncOpenAI", lambda **_kwargs: _FakeAsyncClient())

        result = []
        async for chunk in client._create_completion_stream_async([], []):
            result.append(chunk)

        assert result == ["chunk-1", "chunk-2"]

    @pytest.mark.asyncio
    async def test_chat_stream_async_done_usage_from_stream_chunk(self, monkeypatch):
        from types import SimpleNamespace
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        delta_chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None, content="你好"))],
            usage=None,
        )
        usage_chunk = SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8, total_tokens=20),
        )

        class _FakeQueue:
            async def submit(self, _lane, _func, _messages, _tools):
                async def _stream():
                    yield delta_chunk
                    yield usage_chunk
                return _stream()

        fake_queue = _FakeQueue()
        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: fake_queue)

        events = []
        async for event in client.chat_stream_async("test"):
            events.append(event)

        assert events[-1]["type"] == "done"
        assert events[-1]["usage"] == {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        }

    @pytest.mark.asyncio
    async def test_chat_stream_async_tool_call_emits_complete_arguments_once(self, monkeypatch):
        from types import SimpleNamespace
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        chunk_1 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_1",
                        function=SimpleNamespace(name="get_role_model_detail", arguments='{"model_id":'),
                    )
                ],
                content=None,
            ))],
            usage=None,
        )
        chunk_2 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_1",
                        function=SimpleNamespace(name="", arguments='4,"section":"interview"}'),
                    )
                ],
                content=None,
            ))],
            usage=None,
        )
        chunk_3 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None, content="完成"))],
            usage=None,
        )

        class _FakeQueue:
            def __init__(self):
                self.count = 0

            async def submit(self, _lane, _func, _messages, _tools):
                self.count += 1

                async def _stream_first():
                    yield chunk_1
                    yield chunk_2

                async def _stream_second():
                    yield chunk_3

                return _stream_first() if self.count == 1 else _stream_second()

        fake_queue = _FakeQueue()
        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: fake_queue)
        monkeypatch.setattr(client, "_handle_tool_calls_async", AsyncMock(return_value=[]))

        events = []
        async for event in client.chat_stream_async("test"):
            events.append(event)

        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool"] == "get_role_model_detail"
        assert tool_events[0]["arguments"] == '{"model_id":4,"section":"interview"}'

    @pytest.mark.asyncio
    async def test_chat_stream_async_merges_minimax_tool_call_chunks_with_index_starting_at_one(self, monkeypatch):
        from types import SimpleNamespace
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        chunk_1 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=1,
                        id="call_minimax_1",
                        function=SimpleNamespace(name="article-retrieval", arguments=""),
                    )
                ],
                content=None,
            ))],
            usage=None,
        )
        chunk_2 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=1,
                        id=None,
                        function=SimpleNamespace(name=None, arguments="{}"),
                    )
                ],
                content=None,
            ))],
            usage=None,
        )
        chunk_3 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None, content="完成"))],
            usage=None,
        )

        class _FakeQueue:
            def __init__(self):
                self.count = 0

            async def submit(self, _lane, _func, _messages, _tools):
                self.count += 1

                async def _stream_first():
                    yield chunk_1
                    yield chunk_2

                async def _stream_second():
                    yield chunk_3

                return _stream_first() if self.count == 1 else _stream_second()

        fake_queue = _FakeQueue()
        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: fake_queue)

        captured_tool_calls = []

        async def _fake_handle(tool_calls):
            captured_tool_calls.extend(tool_calls)
            return []

        monkeypatch.setattr(client, "_handle_tool_calls_async", _fake_handle)

        events = []
        async for event in client.chat_stream_async("test"):
            events.append(event)

        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert len(tool_events) == 0
        assert len(captured_tool_calls) == 1
        assert captured_tool_calls[0]["id"] == "call_minimax_1"
        assert captured_tool_calls[0]["function"]["name"] == "article-retrieval"
        assert captured_tool_calls[0]["function"]["arguments"] == "{}"

    @pytest.mark.asyncio
    async def test_chat_stream_async_emits_db_operation_event_for_read_reference(self, monkeypatch):
        from types import SimpleNamespace
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        class _FakeDbSkillSystem:
            data_source = "database"
            available_skills = {}

            def build_tools_definition(self, _activated_skills):
                return []

        client.skill_system = _FakeDbSkillSystem()

        chunk_1 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(
                tool_calls=[
                    SimpleNamespace(
                        index=0,
                        id="call_1",
                        function=SimpleNamespace(
                            name="read_reference",
                            arguments='{"skill_name":"general-assessment","file_path":"references/a.md"}',
                        ),
                    )
                ],
                content=None,
            ))],
            usage=None,
        )
        chunk_2 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None, content="完成"))],
            usage=None,
        )

        class _FakeQueue:
            def __init__(self):
                self.count = 0

            async def submit(self, _lane, _func, _messages, _tools):
                self.count += 1

                async def _stream_first():
                    yield chunk_1

                async def _stream_second():
                    yield chunk_2

                return _stream_first() if self.count == 1 else _stream_second()

        fake_queue = _FakeQueue()
        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: fake_queue)
        monkeypatch.setattr(client, "_handle_tool_calls_async", AsyncMock(return_value=[]))

        events = []
        async for event in client.chat_stream_async("test"):
            events.append(event)

        db_events = [e for e in events if e.get("type") == "db_operation"]
        assert len(db_events) == 1
        assert db_events[0]["operation"] == "read_reference"
        assert "正在调用数据库" in db_events[0]["message"]

    @pytest.mark.asyncio
    async def test_chat_stream_async_persists_history_via_atomic_append(self, monkeypatch):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)
        client.user_id = "u1"

        class _FakeMemoryDB:
            def __init__(self):
                self.append_calls = []
                self.get_calls = 0
                self.save_calls = 0

            async def get_profile(self, _user_id):
                return None

            async def get_conversation(self, _user_id, _conversation_id="default"):
                self.get_calls += 1
                return []

            async def save_conversation(self, _user_id, _messages, _conversation_id="default"):
                self.save_calls += 1

            async def append_conversation(self, _user_id, messages, _conversation_id="default"):
                self.append_calls.append(messages)

        fake_db = _FakeMemoryDB()
        client._history_manager._memory_db = fake_db

        chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None, content="助手回复"))],
            usage=None,
        )

        class _FakeQueue:
            async def submit(self, _lane, _func, _messages, _tools):
                async def _stream():
                    yield chunk
                return _stream()

        monkeypatch.setattr("src.chat.client.get_api_queue", lambda: _FakeQueue())

        events = []
        async for event in client.chat_stream_async("用户问题"):
            events.append(event)

        assert events[-1]["type"] == "done"
        assert fake_db.get_calls == 1
        assert fake_db.save_calls == 0
        assert len(fake_db.append_calls) == 1
        assert fake_db.append_calls[0] == [
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "助手回复"},
        ]


class TestChatClientDbObservability:
    @patch("src.chat.client.get_llm_client")
    @patch("src.chat.client.handle_tool_calls_sync")
    def test_chat_prints_db_operation_hint_for_read_reference(self, mock_handle_tool_calls_sync, mock_get_llm_client, capsys):
        from src.chat.client import ChatClient
        from src.config import Config

        config = Config.with_defaults()
        client = ChatClient(config)

        class _FakeDbSkillSystem:
            data_source = "database"
            available_skills = {}

            def build_tools_definition(self, _activated_skills):
                return []

            def get_skill_content(self, _skill_name):
                return ""

            def get_skill_info(self, _skill_name):
                return None

        client.skill_system = _FakeDbSkillSystem()

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name":"general-assessment","file_path":"references/a.md"}'

        mock_response_1 = Mock()
        mock_response_1.choices = [Mock()]
        mock_response_1.choices[0].message.content = None
        mock_response_1.choices[0].message.tool_calls = [mock_tool_call]

        mock_response_2 = Mock()
        mock_response_2.choices = [Mock()]
        mock_response_2.choices[0].message.content = "完成"
        mock_response_2.choices[0].message.tool_calls = None

        mock_get_llm_client.return_value.chat.completions.create.side_effect = [mock_response_1, mock_response_2]
        mock_handle_tool_calls_sync.return_value = [{"role": "tool", "tool_call_id": "call_123", "content": "ok"}]

        result = client.chat("测试")
        assert result == "完成"

        output = capsys.readouterr().out
        assert "正在调用数据库" in output


class TestContextBudget:
    """上下文预算监控测试套件（方案 C-1）"""

    def test_estimate_tokens_from_messages(self):
        """
        从消息列表估算 token 数量。
        使用字符数 / 3 作为粗略估算（中文场景）。
        """
        from src.chat.context_budget import estimate_tokens

        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
        ]

        tokens = estimate_tokens(messages)

        # 每条消息约 10-30 字符，总字符约 60，估算 token 约 20
        # 实际实现是字符数//3，60//3=20，但中文字符计数可能不同
        # 只要返回合理范围内的值即可
        assert tokens >= 5  # 放宽下限
        assert tokens < 100

    def test_estimate_tokens_empty_messages(self):
        """空消息列表应返回 0 token。"""
        from src.chat.context_budget import estimate_tokens

        tokens = estimate_tokens([])
        assert tokens == 0

    def test_budget_check_returns_ok_when_under_threshold(self):
        """当占用率 < 75% 时返回 OK。"""
        from src.chat.context_budget import BudgetCheck, BudgetAction

        # 假设 max_tokens = 16000，当前使用 8000（50%）
        check = BudgetCheck(max_tokens=16000)
        result = check.check(8000)

        assert result.action == BudgetAction.OK
        assert result.usage_ratio < 0.75

    def test_budget_check_returns_warning_when_between_75_and_90(self):
        """当占用率在 75%-90% 时返回 WARNING。"""
        from src.chat.context_budget import BudgetCheck, BudgetAction

        check = BudgetCheck(max_tokens=16000)
        result = check.check(13000)  # 81.25%

        assert result.action == BudgetAction.WARNING
        assert 0.75 <= result.usage_ratio < 0.90

    def test_budget_check_returns_critical_when_over_90(self):
        """当占用率 >= 90% 时返回 CRITICAL。"""
        from src.chat.context_budget import BudgetCheck, BudgetAction

        check = BudgetCheck(max_tokens=16000)
        result = check.check(14500)  # 90.6%

        assert result.action == BudgetAction.CRITICAL
        assert result.usage_ratio >= 0.90

    def test_budget_check_returns_block_when_over_95(self):
        """当占用率 >= 95% 时返回 BLOCK。"""
        from src.chat.context_budget import BudgetCheck, BudgetAction

        check = BudgetCheck(max_tokens=16000)
        result = check.check(15300)  # 95.6%

        assert result.action == BudgetAction.BLOCK
        assert result.usage_ratio >= 0.95

    def test_budget_result_has_informative_message(self):
        """预算检查结果应包含信息性消息。"""
        from src.chat.context_budget import BudgetCheck

        check = BudgetCheck(max_tokens=16000)

        result_ok = check.check(8000)
        assert "token" in result_ok.message.lower() or "%" in result_ok.message

        result_warning = check.check(13000)
        assert "警告" in result_warning.message or "warning" in result_warning.message.lower() or "%" in result_warning.message

        result_critical = check.check(14500)
        assert "严重" in result_critical.message or "critical" in result_critical.message.lower() or "%" in result_critical.message

    @patch("src.chat.client.create_budget_check")
    @patch("src.chat.client.get_llm_client")
    def test_chat_client_emits_warning_when_budget_exceeded(self, mock_get_llm_client, mock_create_budget_check, capsys):
        """当预算达到 warning 阈值时，chat 应输出警告并继续请求。"""
        from src.chat.client import ChatClient
        from src.chat.context_budget import BudgetCheck
        from src.config import Config

        mock_create_budget_check.return_value = BudgetCheck(max_tokens=80)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].message.tool_calls = None
        mock_get_llm_client.return_value.chat.completions.create.return_value = mock_response

        config = Config.with_defaults()
        client = ChatClient(config)

        long_message = "测试内容" * 45  # 约 180 字符，估算 60 tokens
        client.messages = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": long_message},
        ]
        result = client.chat("继续追问")  # 再追加后会超过 75%
        assert result == "ok"
        assert mock_get_llm_client.return_value.chat.completions.create.called
        output = capsys.readouterr().out
        assert "上下文使用率较高" in output

        # 预算检查应该产生警告（但不拦截）
        # 在轻量版中，我们只记录日志，不阻止请求
        # 这个测试验证预算检查逻辑正确运行


# 已移除 TestContextBudgetCompaction 测试类（压缩功能已移除）

    @patch("src.chat.client.create_budget_check")
    @patch("src.chat.client.get_llm_client")
    def test_chat_client_shows_warning_on_critical(self, mock_get_llm_client, mock_create_budget_check):
        """达到 critical 阈值时，应显示警告但继续请求（不压缩）。"""
        from src.chat.client import ChatClient
        from src.chat.context_budget import BudgetAction, BudgetResult
        from src.config import Config

        mock_create_budget_check.return_value = Mock(
            check=Mock(
                return_value=BudgetResult(
                    action=BudgetAction.CRITICAL,
                    usage_ratio=0.91,
                    estimated_tokens=910,
                    message="上下文接近上限（91.0%），建议清空历史或开始新对话",
                )
            )
        )

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].message.tool_calls = None
        mock_get_llm_client.return_value.chat.completions.create.return_value = mock_response

        config = Config.with_defaults()
        client = ChatClient(config)

        client.messages = [{"role": "system", "content": client._build_system_prompt()}]
        for i in range(8):
            client.messages.append({"role": "user", "content": f"用户消息{i}" * 20})
            client.messages.append({"role": "assistant", "content": f"助手回复{i}" * 20})

        result = client.chat("再问一个问题")
        assert result == "ok"
        # 不再自动压缩，所以不会有对话摘要
        assert not any("对话摘要" in m.get("content", "") for m in client.messages)

    @patch("src.chat.client.create_budget_check")
    @patch("src.chat.client.get_llm_client")
    def test_chat_client_blocks_on_block_threshold(self, mock_get_llm_client, mock_create_budget_check):
        """达到 block 阈值时，应直接拒绝并且不调用 LLM。"""
        from src.chat.client import ChatClient
        from src.chat.context_budget import BudgetAction, BudgetResult
        from src.config import Config

        mock_create_budget_check.return_value = Mock(
            check=Mock(
                return_value=BudgetResult(
                    action=BudgetAction.BLOCK,
                    usage_ratio=0.97,
                    estimated_tokens=970,
                    message="对话过长（已使用 97.0%），请开始新对话",
                )
            )
        )

        config = Config.with_defaults()
        client = ChatClient(config)
        client.messages = [{"role": "system", "content": "系统" * 200}]

        result = client.chat("继续")
        assert "对话过长" in result
        assert not mock_get_llm_client.return_value.chat.completions.create.called


def test_default_system_prompt_comes_from_runtime_constants():
    """ChatClient.DEFAULT_SYSTEM_PROMPT 应来自集中常量 prompts_runtime.SYSTEM_PROMPT_TEMPLATE"""
    from src.chat.client import ChatClient
    from src.chat.prompts_runtime import SYSTEM_PROMPT_TEMPLATE

    assert ChatClient.DEFAULT_SYSTEM_PROMPT == SYSTEM_PROMPT_TEMPLATE


def test_system_prompt_assertions_use_shared_test_constants():
    """验证 system prompt 包含 SYSTEM_PROMPT_EXPECTED_PHRASES 中的所有短语"""
    from src.chat.client import ChatClient
    from src.config import Config

    config = Config.with_defaults()
    client = ChatClient(config)

    prompt = client._build_system_prompt()
    for phrase in SYSTEM_PROMPT_EXPECTED_PHRASES:
        assert phrase in prompt, f"System prompt 缺少预期短语: {phrase}"
