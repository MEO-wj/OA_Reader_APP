"""
数据库技能系统 - 从数据库加载和管理技能

TDD GREEN 阶段：实现通过测试的代码
"""
import json
import logging
import yaml
from typing import Any

from src.core.db import get_pool
from src.core.skill_parser import SkillInfo
from src.core.tool_activation import should_enable_read_reference
from src.chat.prompts_runtime import READ_REFERENCE_TOOL_DESCRIPTION

logger = logging.getLogger(__name__)


class SkillNotFoundError(Exception):
    """技能不存在异常"""
    pass


class DbSkillSystem:
    """数据库技能系统管理类"""
    data_source = "database"

    def __init__(self):
        """
        初始化数据库技能系统
        """
        self.available_skills: dict[str, SkillInfo] = {}

    @classmethod
    async def create(cls, config: Any = None) -> "DbSkillSystem":
        """
        异步工厂方法，创建并加载技能

        Args:
            config: 配置对象（可选，保留兼容性）

        Returns:
            DbSkillSystem 实例

        Raises:
            Exception: 数据库连接失败时
        """
        self = cls()
        await self._load_skills_from_db()
        return self

    async def _load_skills_from_db(self) -> None:
        """
        从数据库加载所有技能

        加载 skills 表中的所有技能记录，解析 metadata 和 tools，
        构建 SkillInfo 对象并存储到 available_skills 中。

        Raises:
            Exception: 数据库连接失败时
        """
        logger.info("[数据库技能系统] 正在连接数据库...")
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, name, metadata, content, tools
                    FROM skills
                    ORDER BY name
                    """
                )

                logger.info(f"[数据库技能系统] 查询到 {len(rows)} 个技能记录")

                for row in rows:
                    # 解析 metadata (JSONB) - asyncpg 返回字符串，需要解析为字典
                    metadata_raw = row["metadata"]
                    if isinstance(metadata_raw, str):
                        metadata = json.loads(metadata_raw)
                    else:
                        metadata = metadata_raw

                    skill_name = metadata.get("name") or row["name"]
                    description = metadata.get("description", "")
                    verification_token = metadata.get("verification_token", "")

                    # 解析 tools (YAML) 获取二级工具
                    secondary_tools = []
                    if row["tools"]:
                        try:
                            yaml_content = yaml.safe_load(row["tools"])
                            if yaml_content and isinstance(yaml_content, dict):
                                secondary_tools = yaml_content.get("tools", [])
                        except yaml.YAMLError:
                            # YAML 解析失败，使用空列表
                            secondary_tools = []

                    # 创建 SkillInfo 对象
                    skill_info = SkillInfo(
                        name=skill_name,
                        description=description,
                        content=row["content"],
                        verification_token=verification_token,
                        path=None,  # 数据库版本没有文件路径
                        secondary_tools=secondary_tools,
                        metadata=metadata if isinstance(metadata, dict) else {},
                    )

                    self.available_skills[skill_name] = skill_info

                logger.info(f"[数据库技能系统] ✓ 已从数据库加载 {len(self.available_skills)} 个技能")

        except Exception as e:
            # 数据库连接失败或查询失败时抛出异常
            raise Exception(f"从数据库加载技能失败: {e}") from e

    def get_skill_content(self, skill_name: str) -> str:
        """
        获取技能内容（同步方法）

        Args:
            skill_name: 技能名称

        Returns:
            技能内容字符串，如果技能不存在则返回空字符串
        """
        skill_info = self.available_skills.get(skill_name)
        if skill_info is None:
            return ""
        return skill_info.content

    def get_skill_info(self, skill_name: str) -> SkillInfo | None:
        """
        获取技能完整信息（同步方法）

        Args:
            skill_name: 技能名称

        Returns:
            SkillInfo 对象，如果技能不存在则返回 None
        """
        return self.available_skills.get(skill_name)

    async def read_reference(self, skill_name: str, file_path: str, lines: str = "") -> str:
        """
        读取技能的参考资料（异步方法）

        Args:
            skill_name: 技能名称
            file_path: 参考资料文件名（相对路径，如 "references/评估/个人评估/MBTI.md"）
            lines: 可选行范围，格式如 "100-200"（数据库版本当前保留参数以兼容接口）

        Returns:
            文件内容字符串，如果技能或文件不存在则返回错误信息

        Raises:
            SkillNotFoundError: 技能不存在时
        """
        # 首先检查技能是否存在
        skill_info = self.available_skills.get(skill_name)
        if skill_info is None:
            return f"错误：技能 '{skill_name}' 不存在"

        try:
            logger.info(f"[数据库技能系统] 正在调用数据库: read_reference {skill_name}/{file_path}")
            logger.debug(f"[数据库技能系统] 正在查询数据库读取 reference: {skill_name}/{file_path}")
            pool = await get_pool()
            async with pool.acquire() as conn:
                # 获取技能 ID
                skill_row = await conn.fetchrow(
                    "SELECT id FROM skills WHERE name = $1",
                    skill_name
                )

                if not skill_row:
                    return f"错误：技能 '{skill_name}' 不存在"

                skill_id = skill_row["id"]

                # 规范化 file_path：移除前导 "references/" 如果存在
                normalized_path = file_path
                if normalized_path.startswith("references/"):
                    normalized_path = normalized_path[len("references/"):]

                # 查询参考资料
                ref_row = await conn.fetchrow(
                    """
                    SELECT content FROM skill_references
                    WHERE skill_id = $1 AND file_path = $2
                    """,
                    skill_id,
                    normalized_path
                )

                if not ref_row:
                    # 文件不存在，列出可用的参考资料
                    ref_rows = await conn.fetch(
                        """
                        SELECT file_path FROM skill_references
                        WHERE skill_id = $1
                        ORDER BY file_path
                        """,
                        skill_id
                    )

                    if ref_rows:
                        available_files = "\n".join(
                            f"  - references/{row['file_path']}" for row in ref_rows
                        )
                        hint = f"\n\n可用的 reference 文件:\n{available_files}"
                    else:
                        hint = f"\n\n该技能没有参考资料"

                    return f"错误：文件 '{file_path}' 不存在{hint}"

                return ref_row["content"]

        except Exception as e:
            return f"错误：读取参考资料失败 - {e}"

    def build_tools_definition(
        self, activated_skills: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        构建 OpenAI tools 定义

        Args:
            activated_skills: 已激活的技能集合，只有这些技能的二级工具会被包含

        Returns:
            符合 OpenAI tools 格式的函数定义列表
        """
        activated = activated_skills or set()
        tools = []

        # 按技能名称排序以保证顺序稳定
        for skill_name in sorted(self.available_skills.keys()):
            skill_info = self.available_skills[skill_name]
            tool = {
                "type": "function",
                "function": {
                    "name": skill_name,
                    "description": skill_info.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
            tools.append(tool)

        if should_enable_read_reference(activated, self.available_skills):
            # 仅在指导性技能激活后添加 read_reference 工具
            tools.append({
                "type": "function",
                "function": {
                    "name": "read_reference",
                    "description": READ_REFERENCE_TOOL_DESCRIPTION,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "技能名称，如 'article-retrieval' 或其他已激活技能"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "references 目录下的相对文件路径，如 'references/评估/个人评估/MBTI.md'。注意：这个路径应该从你调用的技能的 SKILL.md 中获取。"
                            },
                            "lines": {
                                "type": "string",
                                "description": "可选行范围，格式如 '100-200'。仅在需要读取超长文件的特定片段时使用。"
                            }
                        },
                        "required": ["skill_name", "file_path"]
                    },
                },
            })

        # 添加已激活技能的二级工具
        for skill_name in activated:
            skill_info = self.available_skills.get(skill_name)
            if skill_info and skill_info.secondary_tools:
                for tool_def in skill_info.secondary_tools:
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool_def["name"],
                            "description": tool_def["description"],
                            "parameters": tool_def["parameters"],
                        },
                    })

        return tools
