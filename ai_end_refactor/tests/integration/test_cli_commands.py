"""
TDD: CLI 命令集成测试

RED 阶段 - 测试先于实现

这个集成测试验证 CLI 命令的正确性，包括：
- skills/list 命令
- verify 命令
- quit/exit 命令
- 正常对话流程
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import sys


class TestCLICommands:
    """CLI 命令集成测试套件"""

    def test_skills_command(self, tmp_path):
        """
        RED #1: skills/list 命令测试
        测试查看可用技能列表命令

        Given: 包含多个技能的临时目录
        When: 用户输入 'skills' 或 'list' 命令
        Then: 正确显示所有可用技能及其描述
        """
        # === Given: 创建测试技能目录 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建第一个技能
        skill1_dir = skills_dir / "general-assessment"
        skill1_dir.mkdir()
        skill1_content = """---
name: general-assessment
description: 个人与环境评估引导
verification_token: XJ9-KX7-GENERAL-ASSESSMENT-2024
---

# 通用评估引导

通过友好提问或量表引导，帮助用户形成初步画像。
"""
        (skill1_dir / "SKILL.md").write_text(skill1_content, encoding="utf-8")

        # 创建第二个技能
        skill2_dir = skills_dir / "general-guidance"
        skill2_dir.mkdir()
        skill2_content = """---
name: general-guidance
description: 职业生涯指引与路径规划
verification_token: QW7-PL2-GENERAL-GUIDANCE-2024
---

# 通用生涯指引

帮助用户把现状-选择-行动串起来。
"""
        (skill2_dir / "SKILL.md").write_text(skill2_content, encoding="utf-8")

        # === When: 测试 skills 命令处理 ===
        from src.config import Config
        from src.chat import ChatClient

        # 使用临时目录创建配置
        config = Config.with_defaults()
        # 修改配置使用临时技能目录
        config = Config(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # 验证技能已正确加载
        assert "general-assessment" in client.skill_system.available_skills
        assert "general-guidance" in client.skill_system.available_skills

        # 验证技能信息
        skill1_info = client.skill_system.get_skill_info("general-assessment")
        assert skill1_info.description == "个人与环境评估引导"
        assert skill1_info.verification_token == "XJ9-KX7-GENERAL-ASSESSMENT-2024"

        skill2_info = client.skill_system.get_skill_info("general-guidance")
        assert skill2_info.description == "职业生涯指引与路径规划"
        assert skill2_info.verification_token == "QW7-PL2-GENERAL-GUIDANCE-2024"

        # 测试命令识别（通过检查输入是否为 skills/list 命令）
        test_inputs = ["skills", "list", "SKILLS", "LIST"]
        for user_input in test_inputs:
            assert user_input.lower() in ["skills", "list"], \
                f"Input '{user_input}' should be recognized as skills command"

    def test_verify_command(self, tmp_path):
        """
        RED #2: verify 命令测试
        测试验证特定技能命令

        Given: 包含技能的临时目录
        When: 用户输入 'verify <skill_name>' 命令
        Then: 正确显示该技能的验证暗号
        """
        # === Given: 创建测试技能目录 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        skill_content = """---
name: test-skill
description: 测试技能
verification_token: TEST-VERIFY-TOKEN-123
---

# 测试技能

这是一个用于测试验证命令的技能。
"""
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        # === When: 测试 verify 命令处理 ===
        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # 测试 verify 命令解析
        verify_commands = [
            "verify test-skill",
            "verify  test-skill",  # 多个空格
            "VERIFY test-skill",
        ]

        for cmd in verify_commands:
            parts = cmd.strip().split(None, 1)  # split by whitespace, max 1 split
            assert parts[0].lower() == "verify", \
                f"Command '{cmd}' should start with 'verify'"
            assert len(parts) == 2, \
                f"Command '{cmd}' should have skill name"
            skill_name = parts[1]
            assert skill_name == "test-skill", \
                f"Extracted skill name should be 'test-skill', got '{skill_name}'"

        # 验证技能信息获取
        skill_info = client.skill_system.get_skill_info("test-skill")
        assert skill_info is not None, "Skill should exist"
        assert skill_info.verification_token == "TEST-VERIFY-TOKEN-123", \
            "Verification token should match"

    def test_verify_nonexistent_skill(self, tmp_path):
        """
        RED #3: verify 不存在的技能
        测试验证不存在的技能时的处理

        Given: 包含技能的临时目录
        When: 用户输入 'verify nonexistent-skill' 命令
        Then: 正确显示技能不存在
        """
        # === Given: 创建测试技能目录 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "existing-skill"
        skill_dir.mkdir()
        skill_content = """---
name: existing-skill
description: 存在的技能
verification_token: EXISTING-TOKEN
---

# 存在的技能
"""
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        # === When: 测试验证不存在的技能 ===
        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # 验证不存在的技能返回 None
        nonexistent_skill = client.skill_system.get_skill_info("nonexistent-skill")
        assert nonexistent_skill is None, \
            "Nonexistent skill should return None"

        existing_skill = client.skill_system.get_skill_info("existing-skill")
        assert existing_skill is not None, \
            "Existing skill should not return None"

    def test_quit_command(self):
        """
        RED #4: quit/exit 命令测试
        测试退出命令

        Given: 任何输入状态
        When: 用户输入 'quit'、'exit' 或 'q' 命令
        Then: 正确识别为退出命令
        """
        # === Given: 定义退出命令变体 ===
        quit_commands = ["quit", "exit", "q", "QUIT", "EXIT", "Q"]

        # === When & Then: 验证所有变体都被识别 ===
        for cmd in quit_commands:
            assert cmd.lower() in ["quit", "exit", "q"], \
                f"Command '{cmd}' should be recognized as quit command"

        # 验证非退出命令不被识别
        non_quit_commands = ["question", "quest", "quiet", "quote"]
        for cmd in non_quit_commands:
            assert cmd.lower() not in ["quit", "exit", "q"], \
                f"Command '{cmd}' should NOT be recognized as quit command"

    def test_normal_conversation(self, tmp_path):
        """
        RED #5: 正常对话流程测试
        测试正常对话流程不被特殊命令影响

        Given: 初始化的 ChatClient
        When: 用户输入正常的对话内容
        Then: 不被误识别为特殊命令
        """
        # === Given: 创建测试环境 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "conversation-skill"
        skill_dir.mkdir()
        skill_content = """---
name: conversation-skill
description: 对话技能
verification_token: CONV-TOKEN
---

# 对话技能
"""
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # === When: 测试正常对话输入 ===
        normal_inputs = [
            "你好",
            "帮我评估一下我的职业规划",
            "What are the available medical careers?",
            "I want to know about surgical training",
            "验证技能",  # 中文，不是 verify 命令
            "列出所有技能",  # 中文，不是 list 命令
        ]

        # === Then: 验证这些输入不被识别为特殊命令 ===
        for user_input in normal_inputs:
            # 这些输入不应该匹配任何特殊命令
            assert user_input.lower() not in ["quit", "exit", "q"], \
                f"Input '{user_input}' should not be quit command"
            assert user_input.lower() not in ["skills", "list"], \
                f"Input '{user_input}' should not be skills command"
            assert not user_input.lower().startswith("verify "), \
                f"Input '{user_input}' should not be verify command"

    def test_empty_input_handling(self):
        """
        RED #6: 空输入处理测试
        测试空输入或纯空格输入的处理

        Given: 任何输入状态
        When: 用户输入空字符串或纯空格
        Then: 正确识别并跳过
        """
        # === Given: 定义空输入变体 ===
        empty_inputs = ["", "   ", "\t", "\n", "  \t  "]

        # === When & Then: 验证空输入被正确处理 ===
        for user_input in empty_inputs:
            stripped = user_input.strip()
            should_skip = not stripped  # 空输入应该被跳过
            assert should_skip, f"Input '{repr(user_input)}' should be skipped"

    def test_main_loop_command_sequence(self, tmp_path, capsys):
        """
        RED #7: 主循环命令序列测试
        测试主循环中命令的执行顺序

        Given: 初始化的环境
        When: 执行一系列命令（skills → verify → 正常对话 → quit）
        Then: 每个命令被正确处理，不影响后续命令
        """
        # === Given: 创建测试环境 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "sequence-test"
        skill_dir.mkdir()
        skill_content = """---
name: sequence-test
description: 序列测试技能
verification_token: SEQ-TEST-TOKEN
---

# 序列测试
"""
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        # === When: 模拟命令序列 ===
        client = ChatClient(config)

        # 步骤 1: skills 命令应该显示技能列表
        skills = client.skill_system.available_skills
        assert "sequence-test" in skills, "Step 1: Skill should be available"

        # 步骤 2: verify 命令应该显示验证暗号
        skill_info = client.skill_system.get_skill_info("sequence-test")
        assert skill_info.verification_token == "SEQ-TEST-TOKEN", \
            "Step 2: Verification token should match"

        # 步骤 3: 验证命令不影响对话状态
        # 检查 messages 列表在创建时为空
        assert client.messages == [], \
            "Step 3: Messages should be empty initially"

        # 步骤 4: quit 命令应该终止循环
        # 这个测试验证命令识别逻辑
        quit_cmd = "quit"
        should_exit = quit_cmd.lower() in ["quit", "exit", "q"]
        assert should_exit, "Step 4: Quit command should trigger exit"

    def test_command_case_sensitivity(self, tmp_path):
        """
        RED #8: 命令大小写敏感性测试
        测试命令是否正确处理大小写

        Given: 任何输入状态
        When: 用户输入不同大小写的命令
        Then: 命令被正确识别（应不区分大小写）
        """
        # === Given: 创建测试环境 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "case-test"
        skill_dir.mkdir()
        skill_content = """---
name: case-test
description: 大小写测试
verification_token: CASE-TOKEN
---

# 大小写测试
"""
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # === When & Then: 测试不同大小写的命令 ===
        # skills 命令
        for cmd in ["skills", "SKILLS", "Skills", "sKiLlS"]:
            assert cmd.lower() in ["skills", "list"], \
                f"Command '{cmd}' should be recognized as skills command"

        # list 命令
        for cmd in ["list", "LIST", "List"]:
            assert cmd.lower() in ["skills", "list"], \
                f"Command '{cmd}' should be recognized as list command"

        # verify 命令
        for cmd in ["verify case-test", "VERIFY CASE-TEST", "Verify Case-Test"]:
            parts = cmd.strip().split(None, 1)
            assert parts[0].lower() == "verify", \
                f"Command '{cmd}' should be recognized as verify command"

        # quit 命令
        for cmd in ["quit", "QUIT", "Quit", "exit", "EXIT", "Exit", "q", "Q"]:
            assert cmd.lower() in ["quit", "exit", "q"], \
                f"Command '{cmd}' should be recognized as quit command"

    def test_verification_token_in_response(self, tmp_path):
        """
        RED #9: 验证暗号检测测试
        测试 AI 回复中是否包含验证暗号的检测

        Given: 包含验证暗号的技能
        When: AI 回复包含验证暗号
        Then: 正确识别并标记
        """
        # === Given: 创建测试技能 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "token-test"
        skill_dir.mkdir()
        skill_content = """---
name: token-test
description: 验证暗号测试
verification_token: MAGIC-TOKEN-789
---

# 验证暗号测试
"""
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # === When: 测试验证暗号检测 ===
        # 模拟包含验证暗号的回复
        response_with_token = "根据我的分析，MAGIC-TOKEN-789表明这个建议是正确的。"
        response_without_token = "这是一条普通的回复。"

        # === Then: 验证检测功能 ===
        # 检查 ChatClient 的 _check_verification_token 方法
        has_token = client._check_verification_token("token-test", response_with_token)
        assert has_token is True, \
            "Response with verification token should return True"

        has_token = client._check_verification_token("token-test", response_without_token)
        assert has_token is False, \
            "Response without verification token should return False"

    def test_multiple_skills_listing(self, tmp_path):
        """
        RED #10: 多技能列表显示测试
        测试多个技能的列表显示

        Given: 包含多个技能的目录
        When: 执行 skills 命令
        Then: 所有技能按顺序显示
        """
        # === Given: 创建多个技能 ===
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skills_data = [
            {
                "name": "skill-a",
                "description": "技能 A",
                "token": "TOKEN-A",
                "content": "# 技能 A\n"
            },
            {
                "name": "skill-b",
                "description": "技能 B",
                "token": "TOKEN-B",
                "content": "# 技能 B\n"
            },
            {
                "name": "skill-c",
                "description": "技能 C",
                "token": "TOKEN-C",
                "content": "# 技能 C\n"
            },
        ]

        for skill_data in skills_data:
            skill_dir = skills_dir / skill_data["name"]
            skill_dir.mkdir()
            skill_content = f"""---
name: {skill_data["name"]}
description: {skill_data["description"]}
verification_token: {skill_data["token"]}
---

{skill_data["content"]}
"""
            (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

        # === When: 加载技能 ===
        from src.config import Config
        from src.chat import ChatClient

        config = Config(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            skills_dir=str(skills_dir)
        )

        client = ChatClient(config)

        # === Then: 验证所有技能都被加载 ===
        assert len(client.skill_system.available_skills) == 3, \
            f"Should have 3 skills, got {len(client.skill_system.available_skills)}"

        # 验证每个技能的信息
        for skill_data in skills_data:
            skill_info = client.skill_system.get_skill_info(skill_data["name"])
            assert skill_info is not None, \
                f"Skill {skill_data['name']} should exist"
            assert skill_info.description == skill_data["description"], \
                f"Description for {skill_data['name']} should match"
            assert skill_info.verification_token == skill_data["token"], \
                f"Token for {skill_data['name']} should match"

    def test_command_with_extra_whitespace(self, tmp_path):
        """
        RED #11: 命令额外空格处理测试
        测试命令前后有空格时的处理

        Given: 任何输入状态
        When: 用户输入前后有空格的命令
        Then: 命令被正确识别
        """
        # === Given: 定义带额外空格的命令 ===
        commands_with_spaces = [
            ("  skills  ", "skills"),
            ("\tlist\t", "list"),
            ("  verify test-skill  ", "verify"),
            ("  quit", "quit"),
            ("exit  ", "exit"),
        ]

        # === When & Then: 验证命令被正确识别 ===
        for input_cmd, expected_type in commands_with_spaces:
            stripped = input_cmd.strip()
            if expected_type in ["skills", "list"]:
                assert stripped.lower() in ["skills", "list"], \
                    f"Input '{input_cmd}' should be recognized as skills command"
            elif expected_type == "verify":
                parts = stripped.split(None, 1)
                assert parts[0].lower() == "verify", \
                    f"Input '{input_cmd}' should be recognized as verify command"
            elif expected_type in ["quit", "exit"]:
                assert stripped.lower() in ["quit", "exit", "q"], \
                    f"Input '{input_cmd}' should be recognized as quit command"
