"""
TDD: 技能流程集成测试

RED 阶段 - 测试先于实现

这个集成测试验证从扫描到加载的完整技能流程。
"""
import pytest
from pathlib import Path


class TestSkillFlow:
    """技能流程集成测试套件"""

    def test_full_skill_loading_flow(self, tmp_path):
        """
        RED 阶段：完整技能加载流程测试
        测试从扫描到加载的完整流程

        Given: 包含多个技能子目录的临时技能目录
        When: 执行完整流程：扫描 → 解析 → 构建工具定义 → 获取内容
        Then: 每个步骤都正确执行，返回预期的数据结构

        测试预期：
        - 步骤1: 扫描目录，发现所有技能
        - 步骤2: 解析每个 SKILL.md 文件
        - 步骤3: 构建 OpenAI tools 定义
        - 步骤4: 可以获取单个技能的完整内容
        """
        # === Given: 创建测试技能目录结构 ===

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # 创建第一个技能：general-assessment
        skill1_dir = skills_dir / "general-assessment"
        skill1_dir.mkdir()
        skill1_content = """---
name: general-assessment
description: 个人与环境评估引导
verification_token: XJ9-KX7-GENERAL-ASSESSMENT-2024
---

# 通用评估引导

通过友好提问或量表引导，帮助用户形成初步画像。

## 评估维度

1. **个人特质评估**
   - 学习风格与偏好
   - 性格类型测试
   - 价值观排序

2. **环境因素分析**
   - 家庭支持系统
   - 组织资源状况
   - 社会经济背景

3. **能力表现回顾**
   - 基础技能进展
   - 绩效表现评估
   - 协作参与程度
"""
        (skill1_dir / "SKILL.md").write_text(skill1_content, encoding="utf-8")

        # 创建第二个技能：general-guidance
        skill2_dir = skills_dir / "general-guidance"
        skill2_dir.mkdir()
        skill2_content = """---
name: general-guidance
description: 职业生涯指引与路径规划
verification_token: QW7-PL2-GENERAL-GUIDANCE-2024
---

# 通用生涯指引

帮助用户把现状-选择-行动串起来。

## 职业路径

### 专业技术方向
- 高级技能认证
- 专业领域深耕
- 学术 vs 行业应用

### 管理方向
- 团队协作管理
- 项目统筹协调
- 战略规划参与

### 复合路径
- 技术 + 管理
- 技术 + 咨询
- 技术 + 培训
"""
        (skill2_dir / "SKILL.md").write_text(skill2_content, encoding="utf-8")

        # 创建第三个技能：skill-matching
        skill3_dir = skills_dir / "skill-matching"
        skill3_dir.mkdir()
        skill3_content = """---
name: skill-matching
description: 技能匹配与差距分析工具
verification_token: AB3-CD5-MATCHING-2024
---

# 技能匹配分析

根据目标职业要求，分析当前技能储备与目标之间的差距。

## 分析流程

1. 明确目标岗位
2. 提取岗位技能要求
3. 对照个人技能清单
4. 识别能力缺口
5. 制定提升计划
"""
        (skill3_dir / "SKILL.md").write_text(skill3_content, encoding="utf-8")

        # === When: 执行完整流程 ===

        # 这个测试会失败，因为 SkillSystem 类还不存在
        from src.core.skill_system import SkillSystem

        # 初始化系统
        system = SkillSystem(skills_dir=str(skills_dir))

        # 步骤1: 扫描技能目录
        skills = system._scan_skills()

        # 步骤2: 验证扫描结果
        # 步骤3: 构建 OpenAI tools 定义
        tools = system.build_tools_definition()

        # 步骤4: 获取单个技能内容
        skill1_content_result = system.get_skill_content("general-assessment")
        skill2_content_result = system.get_skill_content("general-guidance")
        skill3_info = system.get_skill_info("skill-matching")

        # === Then: 验证每个步骤的结果 ===

        # 验证扫描结果
        assert len(skills) == 3, f"Expected 3 skills, but got {len(skills)}"

        # 验证第一个技能
        skill1 = next((s for s in skills if s.name == "general-assessment"), None)
        assert skill1 is not None, "general-assessment skill not found"
        assert skill1.name == "general-assessment"
        assert skill1.description == "个人与环境评估引导"
        assert skill1.verification_token == "XJ9-KX7-GENERAL-ASSESSMENT-2024"
        assert skill1.path == skill1_dir / "SKILL.md"

        # 验证第二个技能
        skill2 = next((s for s in skills if s.name == "general-guidance"), None)
        assert skill2 is not None, "general-guidance skill not found"
        assert skill2.name == "general-guidance"
        assert skill2.description == "职业生涯指引与路径规划"
        assert skill2.verification_token == "QW7-PL2-GENERAL-GUIDANCE-2024"
        assert skill2.path == skill2_dir / "SKILL.md"

        # 验证第三个技能
        skill3 = next((s for s in skills if s.name == "skill-matching"), None)
        assert skill3 is not None, "skill-matching skill not found"
        assert skill3.name == "skill-matching"
        assert skill3.description == "技能匹配与差距分析工具"
        assert skill3.verification_token == "AB3-CD5-MATCHING-2024"
        assert skill3.path == skill3_dir / "SKILL.md"

        # 验证 tools 定义格式
        assert isinstance(tools, list), "tools should be a list"
        # 未激活指导技能时：应包含 3 个技能 + form_memory
        assert len(tools) == 4, f"Expected 4 tools (3 skills + form_memory), but got {len(tools)}"

        # 验证每个 tool 的结构
        for tool in tools:
            assert tool["type"] == "function", "Tool type should be 'function'"
            assert "function" in tool, "Tool should have 'function' key"
            assert "name" in tool["function"], "Tool function should have 'name'"
            assert "description" in tool["function"], "Tool function should have 'description'"
            assert "parameters" in tool["function"], "Tool function should have 'parameters'"

        # 验证具体技能工具定义
        tool1 = next((t for t in tools if t["function"]["name"] == "general-assessment"), None)
        assert tool1 is not None, "general-assessment tool not found"
        assert tool1["function"]["description"] == "个人与环境评估引导"

        tool2 = next((t for t in tools if t["function"]["name"] == "general-guidance"), None)
        assert tool2 is not None, "general-guidance tool not found"
        assert tool2["function"]["description"] == "职业生涯指引与路径规划"

        tool3 = next((t for t in tools if t["function"]["name"] == "skill-matching"), None)
        assert tool3 is not None, "skill-matching tool not found"
        assert tool3["function"]["description"] == "技能匹配与差距分析工具"

        # 验证 read_reference 工具默认不存在
        read_ref_tool = next((t for t in tools if t["function"]["name"] == "read_reference"), None)
        assert read_ref_tool is None, "read_reference should not be loaded before guidance skill activation"

        # 验证获取技能内容
        assert "# 通用评估引导" in skill1_content_result
        assert "通过友好提问或量表引导" in skill1_content_result
        assert "## 评估维度" in skill1_content_result

        assert "# 通用生涯指引" in skill2_content_result
        assert "帮助用户把现状-选择-行动串起来" in skill2_content_result
        assert "## 职业路径" in skill2_content_result

        # 验证获取技能完整信息
        assert skill3_info.name == "skill-matching"
        assert skill3_info.description == "技能匹配与差距分析工具"
        assert skill3_info.verification_token == "AB3-CD5-MATCHING-2024"
        assert "# 技能匹配分析" in skill3_info.content
        assert "## 分析流程" in skill3_info.content
        assert skill3_info.path == skill3_dir / "SKILL.md"

    def test_skill_flow_with_empty_directory(self, tmp_path):
        """
        RED 阶段：空目录流程测试
        测试空技能目录的处理流程

        Given: 一个空的临时技能目录
        When: 执行扫描和工具定义构建
        Then: 返回空列表，不抛出异常
        """
        # === Given: 创建空技能目录 ===
        skills_dir = tmp_path / "empty_skills"
        skills_dir.mkdir()

        # === When: 执行流程 ===
        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()
        tools = system.build_tools_definition()

        # === Then: 验证结果 ===
        assert isinstance(skills, list), "Skills should be a list"
        assert len(skills) == 0, "Empty directory should return empty list"

        assert isinstance(tools, list), "Tools should be a list"
        # 没有技能时，仍保留 form_memory
        assert len(tools) == 1, "Empty skills should result in 1 tool (form_memory)"

    def test_skill_flow_partial_content(self, tmp_path):
        """
        RED 阶段：部分内容缺失流程测试
        测试技能内容不完整时的处理

        Given: 包含不完整 front matter 的技能目录
        When: 执行扫描和解析
        Then: 使用默认值填充缺失字段，流程继续
        """
        # === Given: 创建部分缺失的技能 ===
        skills_dir = tmp_path / "partial_skills"
        skills_dir.mkdir()

        incomplete_skill_dir = skills_dir / "incomplete-skill"
        incomplete_skill_dir.mkdir()

        # 缺少 verification_token
        incomplete_content = """---
name: incomplete-skill
description: 这是一个不完整的技能
---

# 不完整技能

缺少 verification_token 字段。
"""
        (incomplete_skill_dir / "SKILL.md").write_text(incomplete_content, encoding="utf-8")

        # === When: 执行流程 ===
        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))
        skills = system._scan_skills()
        tools = system.build_tools_definition()

        # === Then: 验证结果 ===
        assert len(skills) == 1
        assert skills[0].name == "incomplete-skill"
        assert skills[0].description == "这是一个不完整的技能"
        # verification_token 应该为空字符串
        assert skills[0].verification_token == ""

        # tools 应该包含 1 个技能 + form_memory
        assert len(tools) == 2
        skill_tools = [t for t in tools if t["function"]["name"] == "incomplete-skill"]
        assert len(skill_tools) == 1
        assert skill_tools[0]["function"]["name"] == "incomplete-skill"

        # 验证 read_reference 工具默认不存在
        read_ref_tools = [t for t in tools if t["function"]["name"] == "read_reference"]
        assert len(read_ref_tools) == 0

    def test_skill_flow_nonexistent_skill_retrieval(self, tmp_path):
        """
        RED 阶段：获取不存在技能的流程测试
        测试获取不存在的技能时的处理

        Given: 已加载技能的系统实例
        When: 尝试获取不存在的技能
        Then: 返回空字符串或 None，不抛出异常
        """
        # === Given: 创建测试环境 ===
        skills_dir = tmp_path / "test_skills"
        skills_dir.mkdir()

        from src.core.skill_system import SkillSystem

        system = SkillSystem(skills_dir=str(skills_dir))

        # === When: 获取不存在的技能 ===
        content = system.get_skill_content("nonexistent-skill")
        info = system.get_skill_info("another-nonexistent-skill")

        # === Then: 验证结果 ===
        assert content == "", "Nonexistent skill content should be empty string"
        assert info is None, "Nonexistent skill info should be None"
