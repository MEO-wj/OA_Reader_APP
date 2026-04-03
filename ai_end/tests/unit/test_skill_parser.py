"""
TDD: 技能解析器单元测试

RED 阶段 - 测试先于实现
"""
import pytest
from pathlib import Path


class TestSkillParser:
    """技能解析器测试套件"""

    def test_parse_yaml_front_matter(self, sample_skill_content):
        """
        RED #1: 正确解析 YAML front matter
        Given: 包含有效 YAML front matter 的 SKILL.md 内容
        When: 调用解析函数
        Then: 返回包含 name, description, content, verification_token 的字典
        """
        # 这个测试会失败，因为 SkillParser 类还不存在
        from src.core.skill_parser import SkillParser

        parser = SkillParser()
        result = parser.parse(sample_skill_content)

        assert result.name == "test-skill"
        assert result.description == "测试技能"
        assert result.verification_token == "TEST-TOKEN-123"
        assert "# 测试技能内容" in result.content
        assert result.content.startswith("# 测试技能内容")

    def test_parse_skill_without_yaml(self, sample_skill_without_yaml):
        """
        RED #2: 无 front matter 时仍能解析
        Given: 没有 YAML front matter 的技能内容
        When: 调用解析函数
        Then: 使用文件名作为 name，内容前 200 字符作为 description
        """
        from src.core.skill_parser import SkillParser

        parser = SkillParser()
        # 文件名作为默认 name
        result = parser.parse(sample_skill_without_yaml, filename="simple-skill")

        assert result.name == "simple-skill"
        assert result.description == sample_skill_without_yaml.replace("\n", " ")[:200]
        assert result.content == sample_skill_without_yaml
        assert result.verification_token == ""

    def test_extract_verification_token(self, sample_skill_content):
        """
        RED #3: 正确提取验证暗号
        Given: 包含 verification_token 的 YAML front matter
        When: 调用解析函数
        Then: verification_token 被正确提取
        """
        from src.core.skill_parser import SkillParser

        parser = SkillParser()
        result = parser.parse(sample_skill_content)

        assert result.verification_token == "TEST-TOKEN-123"

    def test_parse_from_file_path(self, mock_skills_dir):
        """
        RED #4: 从文件路径解析技能
        Given: 存在的 SKILL.md 文件路径
        When: 调用 parse_file 方法
        Then: 返回正确的技能信息字典
        """
        from src.core.skill_parser import SkillParser

        parser = SkillParser()
        skill_path = mock_skills_dir / "test-skill" / "SKILL.md"
        result = parser.parse_file(skill_path)

        assert result.name == "test-skill"
        assert result.verification_token == "MOCK-TOKEN-456"
        assert result.path == skill_path

    def test_parse_multiline_yaml_content(self):
        """
        RED #5: 处理多行 YAML 内容
        Given: YAML front matter 中包含多行 description
        When: 调用解析函数
        Then: 正确提取多行内容
        """
        multi_yaml = """---
name: multi-line-skill
description: 这是一个多行描述
包含多个句子
用于测试解析
verification_token: MULTI-123
---

# 技能内容
"""
        from src.core.skill_parser import SkillParser

        parser = SkillParser()
        result = parser.parse(multi_yaml)

        assert "多行描述" in result.description
        assert result.verification_token == "MULTI-123"

    def test_parse_empty_front_matter(self):
        """
        RED #6: 处理空的 YAML front matter
        Given: 只有 --- 分隔符但没有闭合的 front matter
        When: 调用解析函数
        Then: 整个内容作为普通内容处理
        """
        empty_yaml = """---

# 只有内容
"""
        from src.core.skill_parser import SkillParser

        parser = SkillParser()
        result = parser.parse(empty_yaml, filename="empty-skill")

        assert result.name == "empty-skill"
        # 没有闭合的 ---，所以整个内容被视为普通内容
        assert result.content == empty_yaml
        assert result.verification_token == ""
