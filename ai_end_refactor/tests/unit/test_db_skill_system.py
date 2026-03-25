"""
TDD: 数据库技能系统单元测试

测试 DbSkillSystem 类的功能
"""
import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch


class AsyncContextManager:
    """简单的异步上下文管理器 mock"""
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, *args):
        pass


def create_mock_pool(fetch_results):
    """创建模拟的数据库连接池"""
    mock_pool = MagicMock()
    mock_conn = MagicMock()

    # 配置 fetch 方法为异步
    if isinstance(fetch_results, list):
        mock_conn.fetch = AsyncMock(return_value=fetch_results)
    else:
        # 可以是可调用对象，用于多次调用返回不同值
        mock_conn.fetch = fetch_results

    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
    return mock_pool


@pytest.fixture
def mock_db_rows():
    """模拟数据库返回的技能行数据"""
    return [
        {
            "id": 1,
            "name": "general-assessment",
            "metadata": {
                "name": "general-assessment",
                "description": "个人与环境评估引导",
                "verification_token": "XJ9-KX7-GENERAL-ASSESSMENT-2024",
                "read_reference_parent": True,
            },
            "content": "# 通用评估引导\n\n通过友好提问或量表引导，帮助用户形成初步画像。",
            "tools": None
        },
        {
            "id": 2,
            "name": "general-guidance",
            "metadata": {
                "name": "general-guidance",
                "description": "职业生涯指引与路径规划",
                "verification_token": "QW7-PL2-GENERAL-GUIDANCE-2024",
                "skill_type": "guidance",
            },
            "content": "# 通用生涯指引\n\n帮助用户把现状-选择-行动串起来。",
            "tools": yaml.dump({
                "tools": [
                    {
                        "name": "secondary_tool_1",
                        "description": "二级工具示例",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "param1": {"type": "string"}
                            },
                            "required": ["param1"]
                        }
                    }
                ]
            })
        }
    ]


@pytest.fixture
def mock_reference_rows():
    """模拟数据库返回的参考资料行数据"""
    return [
        {
            "file_path": "评估/个人评估/MBTI.md",
            "content": "# MBTI 测试内容\n这是 MBTI 测试的详细内容。"
        },
        {
            "file_path": "数据/statistics.csv",
            "content": "name,value\ntest,123"
        }
    ]


@pytest.mark.asyncio
class TestDbSkillSystem:
    """DbSkillSystem 测试套件"""

    async def test_create_and_load_skills(self, mock_db_rows):
        """
        测试创建 DbSkillSystem 并从数据库加载技能
        Given: 数据库中有技能记录
        When: 调用 create 方法
        Then: 正确加载所有技能到 available_skills
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            # 创建 DbSkillSystem
            system = await DbSkillSystem.create()

            # 验证技能已加载
            assert len(system.available_skills) == 2
            assert "general-assessment" in system.available_skills
            assert "general-guidance" in system.available_skills

            # 验证技能信息
            skill1 = system.available_skills["general-assessment"]
            assert skill1.description == "个人与环境评估引导"
            assert skill1.verification_token == "XJ9-KX7-GENERAL-ASSESSMENT-2024"
            assert skill1.secondary_tools == []

            skill2 = system.available_skills["general-guidance"]
            assert skill2.description == "职业生涯指引与路径规划"
            assert len(skill2.secondary_tools) == 1
            assert skill2.secondary_tools[0]["name"] == "secondary_tool_1"

    async def test_get_skill_content(self, mock_db_rows):
        """
        测试获取技能内容
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 get_skill_content 方法
        Then: 返回正确的技能内容
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            system = await DbSkillSystem.create()

            # 测试获取存在的技能
            content = system.get_skill_content("general-assessment")
            assert "# 通用评估引导" in content
            assert "通过友好提问或量表引导" in content

            # 测试获取不存在的技能
            content = system.get_skill_content("nonexistent")
            assert content == ""

    async def test_get_skill_info(self, mock_db_rows):
        """
        测试获取技能完整信息
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 get_skill_info 方法
        Then: 返回完整的 SkillInfo 对象
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            system = await DbSkillSystem.create()

            # 测试获取存在的技能
            skill_info = system.get_skill_info("general-guidance")
            assert skill_info is not None
            assert skill_info.name == "general-guidance"
            assert skill_info.description == "职业生涯指引与路径规划"
            assert skill_info.verification_token == "QW7-PL2-GENERAL-GUIDANCE-2024"

            # 测试获取不存在的技能
            skill_info = system.get_skill_info("nonexistent")
            assert skill_info is None

    async def test_build_tools_definition(self, mock_db_rows):
        """
        测试构建 OpenAI tools 定义
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 build_tools_definition 方法
        Then: 返回符合 OpenAI tools 格式的列表
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            system = await DbSkillSystem.create()
            tools = system.build_tools_definition()

            # 验证工具数量：仅 2 个技能（read_reference 仅在指导技能激活后出现）
            assert len(tools) == 2

            # 验证技能工具
            skill_names = [t["function"]["name"] for t in tools]
            assert "general-assessment" in skill_names
            assert "general-guidance" in skill_names
            assert "read_reference" not in skill_names

    async def test_build_tools_definition_includes_read_reference_after_guidance_activation(self, mock_db_rows):
        """
        测试激活指导技能后注入 read_reference 工具
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            system = await DbSkillSystem.create()
            tools = system.build_tools_definition(activated_skills={"general-assessment"})

            read_ref_tool = next(t for t in tools if t["function"]["name"] == "read_reference")
            assert read_ref_tool["type"] == "function"
            assert "description" in read_ref_tool["function"]
            params = read_ref_tool["function"]["parameters"]
            assert "skill_name" in params["properties"]
            assert "file_path" in params["properties"]
            assert "skill_name" in params["required"]
            assert "file_path" in params["required"]

    async def test_build_tools_definition_with_activated_skills(self, mock_db_rows):
        """
        测试构建工具定义时包含已激活技能的二级工具
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 build_tools_definition 并传入激活的技能
        Then: 返回的列表包含已激活技能的二级工具
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            system = await DbSkillSystem.create()

            # 激活 general-guidance（有二级工具）
            tools = system.build_tools_definition(activated_skills={"general-guidance"})

            # 验证工具数量：2个技能 + 1个read_reference + 1个二级工具
            assert len(tools) == 4

            # 验证二级工具
            secondary_tool = next(
                (t for t in tools if t["function"]["name"] == "secondary_tool_1"),
                None
            )
            assert secondary_tool is not None
            assert secondary_tool["function"]["description"] == "二级工具示例"

    async def test_read_reference_success(self, mock_db_rows, mock_reference_rows):
        """
        测试成功读取参考资料
        Given: 已加载技能的 DbSkillSystem 实例，数据库中有参考资料
        When: 调用 read_reference 方法
        Then: 返回参考资料内容
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            # 第一次调用：加载技能
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            # 第二次调用：读取参考资料
            # 创建一个新的 mock 用于 read_reference
            call_count = [0]
            async def fetch_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # 获取技能ID
                    return {"id": 1, "name": "general-assessment"}
                else:
                    # 返回参考资料
                    return mock_reference_rows[0]

            mock_pool = MagicMock()
            mock_conn = MagicMock()
            mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)
            mock_conn.fetchrow = AsyncMock(side_effect=fetch_side_effect)
            mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
            mock_get_pool.return_value = mock_pool

            content = await system.read_reference("general-assessment", "references/评估/个人评估/MBTI.md")

            assert "# MBTI 测试内容" in content
            assert "这是 MBTI 测试的详细内容" in content

    async def test_read_reference_with_normalized_path(self, mock_db_rows, mock_reference_rows):
        """
        测试读取参考资料时路径规范化（移除 references/ 前缀）
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 read_reference 时使用带 references/ 前缀的路径
        Then: 正确匹配数据库中的文件名（无前缀）
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            # 第一次调用：加载技能
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            # 第二次调用：读取参考资料
            call_count = [0]
            async def fetch_side_effect(query, *args):
                call_count[0] += 1
                if call_count[0] == 1:
                    # 获取技能ID
                    return {"id": 1}
                else:
                    # 返回参考资料（使用规范化的路径查询）
                    return mock_reference_rows[0]

            mock_pool = MagicMock()
            mock_conn = MagicMock()
            mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)
            mock_conn.fetchrow = AsyncMock(side_effect=fetch_side_effect)
            mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
            mock_get_pool.return_value = mock_pool

            # 使用带 references/ 前缀的路径
            content = await system.read_reference("general-assessment", "references/评估/个人评估/MBTI.md")

            assert "# MBTI 测试内容" in content

    async def test_read_reference_accepts_lines_parameter(self, mock_db_rows, mock_reference_rows):
        """
        测试 read_reference 兼容第三个 lines 参数
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 read_reference 并传入 lines 参数
        Then: 不抛异常，正常返回参考资料内容
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            # 第一次调用：加载技能
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            # 第二次调用：读取参考资料
            call_count = [0]

            async def fetch_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    return {"id": 1}
                return mock_reference_rows[0]

            mock_pool = MagicMock()
            mock_conn = MagicMock()
            mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)
            mock_conn.fetchrow = AsyncMock(side_effect=fetch_side_effect)
            mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
            mock_get_pool.return_value = mock_pool

            content = await system.read_reference(
                "general-assessment",
                "references/评估/个人评估/MBTI.md",
                "1-20",
            )

            assert "# MBTI 测试内容" in content

    async def test_read_reference_file_not_found(self, mock_db_rows):
        """
        测试读取不存在的参考资料
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 read_reference 但文件不存在
        Then: 返回错误信息，包含可用文件列表
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            # 第一次调用：加载技能
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            # 第二次调用：读取不存在的参考资料
            call_count = [0]
            async def fetch_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # 获取技能ID
                    return {"id": 1}
                elif call_count[0] == 2:
                    # 查询参考资料（返回空）
                    return None
                else:
                    # 列出可用文件
                    return [{"file_path": "评估/个人评估/MBTI.md"}]

            mock_pool = MagicMock()
            mock_conn = MagicMock()
            mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)
            mock_conn.fetchrow = AsyncMock(side_effect=fetch_side_effect)
            mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
            mock_get_pool.return_value = mock_pool

            result = await system.read_reference("general-assessment", "references/nonexistent.md")

            assert "错误" in result
            assert "nonexistent.md" in result
            assert "可用的 reference 文件" in result
            assert "评估/个人评估/MBTI.md" in result

    async def test_read_reference_skill_not_found(self, mock_db_rows):
        """
        测试读取不存在技能的参考资料
        Given: DbSkillSystem 实例
        When: 调用 read_reference 但技能不存在
        Then: 返回错误信息
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            result = await system.read_reference("nonexistent-skill", "references/test.md")

            assert "错误" in result
            assert "nonexistent-skill" in result
            assert "不存在" in result

    async def test_load_skills_handles_invalid_yaml(self):
        """
        测试加载技能时处理无效的 YAML tools
        Given: 数据库中包含无效 YAML 的 tools 字段
        When: 调用 create 方法
        Then: 跳过解析失败的 tools，继续加载技能
        """
        invalid_tools_row = {
            "id": 1,
            "name": "test-skill",
            "metadata": {
                "name": "test-skill",
                "description": "测试技能",
                "verification_token": "TEST-123"
            },
            "content": "# 测试内容",
            "tools": "invalid: yaml: content: ["
        }

        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool([invalid_tools_row])

            system = await DbSkillSystem.create()

            # 验证技能已加载，但 secondary_tools 为空
            assert "test-skill" in system.available_skills
            skill = system.available_skills["test-skill"]
            assert skill.secondary_tools == []

    async def test_load_skills_from_database_error(self):
        """
        测试数据库连接失败时的处理
        Given: 数据库连接失败
        When: 调用 create 方法
        Then: 抛出异常
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.side_effect = Exception("数据库连接失败")

            with pytest.raises(Exception) as exc_info:
                await DbSkillSystem.create()

            assert "从数据库加载技能失败" in str(exc_info.value)

    async def test_read_reference_no_references_available(self, mock_db_rows):
        """
        测试技能没有参考资料时的情况
        Given: 已加载技能的 DbSkillSystem 实例，技能没有参考资料
        When: 调用 read_reference
        Then: 返回错误信息，说明没有参考资料
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            # 第一次调用：加载技能
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            # 第二次调用：读取不存在的参考资料
            call_count = [0]
            async def fetch_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # 获取技能ID
                    return {"id": 1}
                elif call_count[0] == 2:
                    # 查询参考资料（返回空）
                    return None
                else:
                    # 列出可用文件（返回空）
                    return []

            mock_pool = MagicMock()
            mock_conn = MagicMock()
            mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)
            mock_conn.fetchrow = AsyncMock(side_effect=fetch_side_effect)
            mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
            mock_get_pool.return_value = mock_pool

            result = await system.read_reference("general-assessment", "references/test.md")

            assert "错误" in result
            assert "没有参考资料" in result

    async def test_read_reference_database_error(self, mock_db_rows):
        """
        测试读取参考资料时数据库错误
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 read_reference 但数据库查询失败
        Then: 返回错误信息
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            # 第一次调用：加载技能
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)
            system = await DbSkillSystem.create()

            # 第二次调用：数据库查询失败
            mock_pool = MagicMock()
            mock_conn = MagicMock()
            mock_conn.fetchrow = MagicMock(side_effect=Exception("数据库错误"))
            mock_pool.acquire.return_value = AsyncContextManager(mock_conn)
            mock_get_pool.return_value = mock_pool

            result = await system.read_reference("general-assessment", "references/test.md")

            assert "错误" in result
            assert "读取参考资料失败" in result

    async def test_metadata_fallback_to_row_name(self):
        """
        测试当 metadata 中没有 name 字段时，使用 row['name']
        Given: 数据库中 metadata 缺少 name 字段
        When: 调用 create 方法
        Then: 使用 row['name'] 作为技能名称
        """
        row_without_name = {
            "id": 1,
            "name": "fallback-name",
            "metadata": {
                "description": "测试描述",
                "verification_token": "TOKEN-123"
            },
            "content": "# 内容",
            "tools": None
        }

        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool([row_without_name])

            system = await DbSkillSystem.create()

            # 验证使用了 row['name'] 作为技能名称
            assert "fallback-name" in system.available_skills
            skill = system.available_skills["fallback-name"]
            assert skill.name == "fallback-name"

    async def test_empty_database(self):
        """
        测试数据库中没有技能时的情况
        Given: 数据库中没有技能记录
        When: 调用 create 方法
        Then: available_skills 为空字典
        """
        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool([])

            system = await DbSkillSystem.create()

            assert len(system.available_skills) == 0
            assert system.get_skill_content("any") == ""
            assert system.get_skill_info("any") is None


# 导入被测试的类
from src.core.db_skill_system import DbSkillSystem
from src.core.tool_activation import should_enable_read_reference
from src.core.skill_parser import SkillInfo


class TestReadReferenceActivation:
    """read_reference 激活条件测试套件"""

    def test_read_reference_enabled_only_for_guidance_skill(self):
        """
        测试 read_reference 仅在指导技能激活后启用
        Given: 已激活技能集合和可用技能元数据
        When: 调用 should_enable_read_reference
        Then: 仅指导技能激活时返回 True
        """
        available_skills = {
            "guidance-skill": SkillInfo(
                name="guidance-skill",
                description="指导技能",
                content="# guidance",
                verification_token="",
                metadata={"read_reference_parent": True},
            ),
            "document-retrieval": SkillInfo(
                name="document-retrieval",
                description="检索技能",
                content="# retrieval",
                verification_token="",
                metadata={},
            ),
        }

        assert should_enable_read_reference({"guidance-skill"}, available_skills) is True
        assert should_enable_read_reference({"document-retrieval"}, available_skills) is False

    def test_read_reference_disabled_when_no_skills_activated(self):
        """
        测试 read_reference 在没有技能激活时禁用
        Given: 空的已激活技能集合
        When: 调用 should_enable_read_reference
        Then: 返回 False
        """
        assert should_enable_read_reference(set(), {}) is False
        assert should_enable_read_reference(frozenset(), {}) is False


class TestReadReferenceToolDescriptionCentralized:
    """Task 5: read_reference 工具描述集中化测试"""

    async def test_db_skill_system_read_reference_description_is_centralized(self, mock_db_rows):
        """
        Task 5: 验证 DbSkillSystem 的 read_reference 工具描述使用集中化的常量
        Given: 已加载技能的 DbSkillSystem 实例
        When: 调用 build_tools_definition 并激活指导技能
        Then: read_reference 工具的 description 等于 READ_REFERENCE_TOOL_DESCRIPTION
        """
        from src.chat.prompts_runtime import READ_REFERENCE_TOOL_DESCRIPTION

        with patch("src.core.db_skill_system.get_pool") as mock_get_pool:
            mock_get_pool.return_value = create_mock_pool(mock_db_rows)

            system = await DbSkillSystem.create()
            tools = system.build_tools_definition(activated_skills={"general-assessment"})

            rr = [t for t in tools if t.get("function", {}).get("name") == "read_reference"][0]
            assert rr["function"]["description"] == READ_REFERENCE_TOOL_DESCRIPTION
