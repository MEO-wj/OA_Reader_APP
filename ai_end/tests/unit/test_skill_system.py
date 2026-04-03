"""
TDD: 技能系统单元测试

RED 阶段 - 测试先于实现
"""
import pytest
from pathlib import Path


class TestSkillSystem:
    """技能系统测试套件"""

    def test_scan_skills_directory(self, tmp_path):
        """
        RED #1: 扫描 skills 目录，加载所有技能
        Given: 包含多个技能子目录的 skills 目录
        When: 创建 SkillSystem 并调用 _scan_skills
        Then: 正确加载所有技能，返回 SkillInfo 列表
        """
        # 创建测试目录结构
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建第一个技能
        skill1_dir = skills_dir / "general-assessment"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text("""---
name: general-assessment
description: 通用个人与环境评估引导
verification_token: XJ9-KX7-GENERAL-ASSESSMENT-2024
---

# 通用评估引导

通过友好提问或量表引导，帮助用户形成初步画像。
""", encoding="utf-8")

        # 创建第二个技能
        skill2_dir = skills_dir / "general-guidance"
        skill2_dir.mkdir()
        (skill2_dir / "SKILL.md").write_text("""---
name: general-guidance
description: 通用职业发展指引与路径规划
verification_token: QW7-PL2-GENERAL-GUIDANCE-2024
---

# 通用发展指引

帮助用户把现状-选择-行动串起来。
""", encoding="utf-8")

        # 这个测试会失败，因为 SkillSystem 类还不存在
        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()

        assert len(skills) == 2
        skill_names = {skills[0].name, skills[1].name}
        assert skill_names == {"general-assessment", "general-guidance"}
        verification_tokens = {skills[0].verification_token, skills[1].verification_token}
        assert verification_tokens == {"XJ9-KX7-GENERAL-ASSESSMENT-2024", "QW7-PL2-GENERAL-GUIDANCE-2024"}

    def test_build_tools_definition(self, tmp_path):
        """
        RED #2: 生成 OpenAI tools 定义
        Given: 已加载技能的 SkillSystem 实例
        When: 调用 build_tools_definition 方法
        Then: 返回符合 OpenAI tools 格式的列表，包含技能、read_reference、search_policies、grep_policy 工具
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能描述
verification_token: TEST-TOKEN-123
---

# 测试技能内容

这是一个测试技能。
""", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        tools = system.build_tools_definition()

        assert isinstance(tools, list)
        # 应该包含 1 个技能 + form_memory（read_reference 仅在指导技能激活后出现）
        tool_names = {t["function"]["name"] for t in tools}
        assert {"test-skill", "form_memory"}.issubset(tool_names)
        assert "read_reference" not in tool_names

        # 找到技能工具
        skill_tools = [t for t in tools if t["function"]["name"] == "test-skill"]
        assert len(skill_tools) == 1
        assert skill_tools[0]["type"] == "function"
        assert "function" in skill_tools[0]
        assert skill_tools[0]["function"]["name"] == "test-skill"
        assert "description" in skill_tools[0]["function"]
        assert "parameters" in skill_tools[0]["function"]

    def test_get_skill_content(self, tmp_path):
        """
        RED #3: 获取技能内容
        Given: 已加载技能的 SkillSystem 实例
        When: 调用 get_skill_content 方法并传入技能名称
        Then: 返回该技能的完整内容字符串
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "content-skill"
        skill_dir.mkdir()
        test_content = """---
name: content-skill
description: 内容测试技能
verification_token: CONTENT-123
---

# 技能内容标题

这是技能的具体内容。

包含多个段落。

## 子章节

子章节内容。
"""
        (skill_dir / "SKILL.md").write_text(test_content, encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        content = system.get_skill_content("content-skill")

        assert "# 技能内容标题" in content
        assert "这是技能的具体内容" in content
        assert "## 子章节" in content
        assert "子章节内容" in content

    def test_get_skill_info(self, tmp_path):
        """
        RED #4: 获取技能完整信息
        Given: 已加载技能的 SkillSystem 实例
        When: 调用 get_skill_info 方法并传入技能名称
        Then: 返回包含所有字段的 SkillInfo 对象
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "info-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: info-skill
description: 完整信息测试技能
verification_token: INFO-TOKEN-456
---

# 信息测试技能

用于测试获取完整技能信息。
""", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skill_info = system.get_skill_info("info-skill")

        assert skill_info.name == "info-skill"
        assert skill_info.description == "完整信息测试技能"
        assert skill_info.verification_token == "INFO-TOKEN-456"
        assert "# 信息测试技能" in skill_info.content
        assert skill_info.path == skill_dir / "SKILL.md"

    def test_skill_system_with_nonexistent_directory(self):
        """
        RED #5: 处理不存在的目录
        Given: 一个不存在的目录路径
        When: 创建 SkillSystem 实例
        Then: 应该优雅处理或抛出适当异常
        """
        from src.core.skill_system import SkillSystem

        # 不存在的目录
        system = SkillSystem(skills_dir="/nonexistent/skills/path")
        skills = system._scan_skills()

        # 应该返回空列表而不是崩溃
        assert isinstance(skills, list)
        assert len(skills) == 0

    def test_skill_system_with_empty_directory(self, tmp_path):
        """
        RED #6: 处理空目录
        Given: 一个空的 skills 目录
        When: 创建 SkillSystem 并调用 _scan_skills
        Then: 返回空列表
        """
        # 创建空目录
        skills_dir = tmp_path / "empty_skills"
        skills_dir.mkdir()

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()

        assert isinstance(skills, list)
        assert len(skills) == 0

    def test_get_nonexistent_skill_content(self, tmp_path):
        """
        RED #7: 获取不存在的技能内容
        Given: 已初始化的 SkillSystem 实例
        When: 调用 get_skill_content 传入不存在的技能名
        Then: 返回空字符串或抛出 KeyError
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        content = system.get_skill_content("nonexistent-skill")

        # 应该返回空字符串
        assert content == ""

    def test_get_nonexistent_skill_info(self, tmp_path):
        """
        RED #8: 获取不存在的技能信息
        Given: 已初始化的 SkillSystem 实例
        When: 调用 get_skill_info 传入不存在的技能名
        Then: 返回 None 或抛出 KeyError
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skill_info = system.get_skill_info("nonexistent-skill")

        # 应该返回 None
        assert skill_info is None

    def test_default_skills_directory(self):
        """
        RED #9: 使用默认 skills 目录
        Given: 不指定 skills_dir 参数
        When: 创建 SkillSystem 实例
        Then: 使用默认的 "./skills" 目录
        """
        from src.core.skill_system import SkillSystem

        # 使用默认目录创建实例
        system = SkillSystem()

        # 验证使用了正确的默认路径
        assert system.skills_dir == "./skills"

    def test_build_tools_definition_multiple_skills(self, tmp_path):
        """
        RED #10: 为多个技能生成 tools 定义
        Given: 包含多个技能的 SkillSystem 实例
        When: 调用 build_tools_definition 方法
        Then: 返回包含所有技能定义的列表，每个都有正确的格式，外加 form_memory 工具
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建多个技能
        for i in range(3):
            skill_dir = skills_dir / f"skill-{i}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(f"""---
name: skill-{i}
description: 技能{i}的描述
verification_token: TOKEN-{i}
---

# 技能 {i}

这是技能 {i} 的内容。
""", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        tools = system.build_tools_definition()

        # 应该包含 3 个技能 + form_memory（read_reference 仅在指导技能激活后出现）
        tool_names = {t["function"]["name"] for t in tools}
        assert "form_memory" in tool_names
        assert "read_reference" not in tool_names
        assert len([n for n in tool_names if n.startswith("skill-")]) == 3
        for i in range(3):
            assert tools[i]["type"] == "function"
            assert tools[i]["function"]["name"] == f"skill-{i}"
            assert tools[i]["function"]["description"] == f"技能{i}的描述"
            assert "parameters" in tools[i]["function"]

    def test_scan_skills_skips_files_in_directory(self, tmp_path):
        """
        RED #11: 扫描时跳过目录中的文件（非目录）
        Given: skills 目录中包含文件和非目录条目
        When: 调用 _scan_skills
        Then: 跳过非目录条目，只处理子目录
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建一个有效的技能目录
        skill_dir = skills_dir / "valid-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: valid-skill
description: 有效技能
---
# 内容
""", encoding="utf-8")

        # 在 skills 目录下创建一个文件（不是目录）
        (skills_dir / "README.md").write_text("# 这是一个说明文件", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()

        # 应该只加载有效的技能目录，跳过 README.md 文件
        assert len(skills) == 1
        assert skills[0].name == "valid-skill"

    def test_scan_skills_skips_directories_without_skill_md(self, tmp_path):
        """
        RED #12: 扫描时跳过没有 SKILL.md 的目录
        Given: skills 目录中包含空子目录
        When: 调用 _scan_skills
        Then: 跳过没有 SKILL.md 的目录
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建一个有效的技能目录
        skill_dir = skills_dir / "valid-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: valid-skill
description: 有效技能
---
# 内容
""", encoding="utf-8")

        # 创建一个空的子目录（没有 SKILL.md）
        empty_dir = skills_dir / "empty-directory"
        empty_dir.mkdir()

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()

        # 应该只加载有效的技能目录，跳过空目录
        assert len(skills) == 1
        assert skills[0].name == "valid-skill"

    def test_read_reference_file_success(self, tmp_path):
        """
        RED #14: 成功读取 reference 文件
        Given: 一个有 references 文件的技能
        When: 调用 read_reference 方法
        Then: 返回文件内容
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()

        # 创建 SKILL.md
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---

# 内容
""", encoding="utf-8")

        # 创建 references 目录和文件
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        test_file = refs_dir / "评估" / "个人评估" / "MBTI.md"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("# MBTI 测试内容\n这是 MBTI 测试的详细内容。", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        content = system.read_reference("test-skill", "references/评估/个人评估/MBTI.md")

        assert "# MBTI 测试内容" in content
        assert "这是 MBTI 测试的详细内容" in content

    def test_read_reference_file_not_found(self, tmp_path):
        """
        RED #15: 读取不存在的 reference 文件
        Given: 一个技能
        When: 调用 read_reference 传入不存在的文件路径
        Then: 返回错误信息，包含可用文件列表
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---

# 内容
""", encoding="utf-8")

        # 创建 references 目录和文件
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        test_file = refs_dir / "existing.md"
        test_file.write_text("现有文件内容", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        result = system.read_reference("test-skill", "references/nonexistent.md")

        assert "错误" in result
        assert "nonexistent.md" in result
        assert "existing.md" in result

    def test_read_reference_skill_not_found(self, tmp_path):
        """
        RED #16: 读取不存在的技能的 reference 文件
        Given: SkillSystem 实例
        When: 调用 read_reference 传入不存在的技能名
        Then: 返回错误信息
        """
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        result = system.read_reference("nonexistent-skill", "references/test.md")

        assert "错误" in result
        assert "nonexistent-skill" in result

    def test_read_reference_no_references_directory(self, tmp_path):
        """
        RED #17: 技能没有 references 目录
        Given: 一个没有 references 目录的技能
        When: 调用 read_reference
        Then: 返回错误信息，说明没有 references 目录
        """
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---

# 内容
""", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        result = system.read_reference("test-skill", "references/test.md")

        assert "错误" in result
        assert "没有 references 目录" in result

    def test_build_tools_definition_includes_read_reference_when_guidance_skill_activated(self, tmp_path):
        """
        RED #18: build_tools_definition 包含 read_reference 工具
        Given: 包含指导技能的 SkillSystem 实例
        When: 调用 build_tools_definition 并激活指导技能
        Then: 返回的列表包含 read_reference 工具定义
        """
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        guidance_skill_dir = skills_dir / "general-assessment"
        guidance_skill_dir.mkdir()
        (guidance_skill_dir / "SKILL.md").write_text("""---
name: general-assessment
description: 个人与环境评估引导
read_reference_parent: true
---
# 内容
""", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        tools = system.build_tools_definition(activated_skills={"general-assessment"})

        # 应该包含 read_reference 工具
        read_reference_tools = [t for t in tools if t["function"]["name"] == "read_reference"]
        assert len(read_reference_tools) == 1

        tool = read_reference_tools[0]
        assert tool["type"] == "function"
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

        # 检查参数定义
        params = tool["function"]["parameters"]
        assert "properties" in params
        assert "skill_name" in params["properties"]
        assert "file_path" in params["properties"]
        assert "required" in params
        assert "skill_name" in params["required"]
        assert "file_path" in params["required"]

    def test_build_tools_definition_does_not_include_read_reference_for_non_guidance_skill(self, tmp_path):
        """
        RED #18-2: 非指导技能激活时不应注入 read_reference
        """
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---

# 内容
""", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        tools = system.build_tools_definition(activated_skills={"test-skill"})

        tool_names = {t["function"]["name"] for t in tools}
        assert "read_reference" not in tool_names

    def test_read_reference_with_csv_file(self, tmp_path):
        """
        RED #19: 读取 CSV 格式的 reference 文件
        Given: 一个有 CSV reference 文件的技能
        When: 调用 read_reference 读取 CSV 文件
        Then: 正确返回 CSV 内容
        """
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---

# 内容
""", encoding="utf-8")

        # 创建 CSV 文件
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        csv_file = refs_dir / "data.csv"
        csv_file.write_text("name,value\ntest,123", encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        content = system.read_reference("test-skill", "references/data.csv")

        assert "name,value" in content
        assert "test,123" in content

    def test_read_reference_with_json_file(self, tmp_path):
        """
        RED #20: 读取 JSON 格式的 reference 文件
        Given: 一个有 JSON reference 文件的技能
        When: 调用 read_reference 读取 JSON 文件
        Then: 正确返回 JSON 内容
        """
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
---

# 内容
""", encoding="utf-8")

        # 创建 JSON 文件
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        json_file = refs_dir / "data.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        content = system.read_reference("test-skill", "references/data.json")

        assert '{"key": "value"}' in content

    def test_scan_skills_handles_parsing_errors(self, tmp_path, monkeypatch):
        """
        RED #13: 扫描时处理文件解析错误
        Given: skills 目录中包含一个会触发 parse_file 异常的 SKILL.md
        When: 调用 _scan_skills
        Then: 跳过解析失败的技能，继续处理其他技能
        """
        # 创建测试目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建一个有效的技能目录
        valid_dir = skills_dir / "valid-skill"
        valid_dir.mkdir()
        (valid_dir / "SKILL.md").write_text("""---
name: valid-skill
description: 有效技能
---
# 内容
""", encoding="utf-8")

        # 创建一个用于触发解析异常的技能目录
        broken_dir = skills_dir / "no-permission-skill"
        broken_dir.mkdir()
        broken_file = broken_dir / "SKILL.md"
        broken_file.write_text("content", encoding="utf-8")

        from src.core.skill_parser import SkillParser
        from src.core.skill_system import SkillSystem

        original_parse_file = SkillParser.parse_file

        def fake_parse_file(self, file_path):
            if file_path == broken_file:
                raise PermissionError("permission denied")
            return original_parse_file(self, file_path)

        monkeypatch.setattr(SkillParser, "parse_file", fake_parse_file)

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()

        # 应该只加载有效的技能，跳过解析失败的文件
        assert len(skills) == 1
        assert skills[0].name == "valid-skill"


def test_read_reference_tool_description_is_centralized(tmp_path):
    """
    Task 5: 验证 read_reference 工具描述使用集中化的常量
    Given: 包含指导技能的 SkillSystem 实例
    When: 调用 build_tools_definition 并激活指导技能
    Then: read_reference 工具的 description 等于 READ_REFERENCE_TOOL_DESCRIPTION
    """
    from src.chat.prompts_runtime import READ_REFERENCE_TOOL_DESCRIPTION
    from src.core.skill_system import SkillSystem

    # 创建测试目录
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    guidance_skill_dir = skills_dir / "general-assessment"
    guidance_skill_dir.mkdir()
    (guidance_skill_dir / "SKILL.md").write_text("""---
name: general-assessment
description: 个人与环境评估引导
read_reference_parent: true
---
# 内容
""", encoding="utf-8")

    system = SkillSystem(skills_dir=str(skills_dir))
    tools = system.build_tools_definition(activated_skills={"general-assessment"})

    rr = [t for t in tools if t.get("function", {}).get("name") == "read_reference"][0]
    assert rr["function"]["description"] == READ_REFERENCE_TOOL_DESCRIPTION
