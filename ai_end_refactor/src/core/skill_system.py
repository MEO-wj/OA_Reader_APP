"""
技能系统 - 文件系统版本（已废弃）

请使用 DbSkillSystem 替代

DEPRECATED: 此模块已废弃，请使用 src.core.db_skill_system.DbSkillSystem
"""
import warnings

warnings.warn(
    "SkillSystem (文件系统版本) 已废弃，请使用 DbSkillSystem",
    DeprecationWarning,
    stacklevel=2
)

import yaml
from pathlib import Path
from typing import Any

from src.core.skill_parser import SkillInfo, SkillParser
from src.core.tool_activation import should_enable_read_reference
from src.chat.prompts_runtime import READ_REFERENCE_TOOL_DESCRIPTION


class SkillSystem:
    """技能系统管理类"""

    def __init__(self, skills_dir: str = "./skills"):
        """
        初始化技能系统

        Args:
            skills_dir: 技能目录路径，默认为 "./skills"
        """
        self.skills_dir = skills_dir
        self._skills_dir_path = Path(skills_dir)
        self.available_skills: dict[str, SkillInfo] = {}
        self.parser = SkillParser()
        self._scan_skills()
        self._load_secondary_tools()  # 预加载所有技能的二级工具定义

    def _scan_skills(self) -> list[SkillInfo]:
        """
        扫描 skills 目录，加载所有技能

        Returns:
            加载的技能列表
        """
        skills = []

        # 检查目录是否存在
        if not self._skills_dir_path.exists():
            return skills

        # 遍历 skills 目录下的所有子目录
        for skill_dir in self._skills_dir_path.iterdir():
            if not skill_dir.is_dir():
                continue

            # 查找 SKILL.md 文件
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                # 解析技能文件
                skill_info = self.parser.parse_file(skill_file)
                self.available_skills[skill_info.name] = skill_info
                skills.append(skill_info)
            except Exception:
                # 如果解析失败，跳过该技能
                continue

        return skills

    def parse_tools(self, skill_name: str) -> list[dict[str, Any]]:
        """
        解析技能的 TOOLS.md 文件

        Args:
            skill_name: 技能名称

        Returns:
            二级工具定义列表，解析失败或文件不存在时返回空列表
        """
        skill_info = self.available_skills.get(skill_name)
        if not skill_info or not skill_info.path:
            return []

        tools_file = skill_info.path.parent / "TOOLS.md"
        if not tools_file.exists():
            return []

        try:
            content = tools_file.read_text(encoding="utf-8")
            yaml_content = yaml.safe_load(content)
            return yaml_content.get('tools', []) if yaml_content else []
        except (yaml.YAMLError, IOError):
            return []

    def _load_secondary_tools(self):
        """
        为所有技能预加载二级工具定义

        将每个技能的 TOOLS.md 中定义的工具加载到 SkillInfo.secondary_tools 中
        """
        for skill_name in self.available_skills:
            tools = self.parse_tools(skill_name)
            self.available_skills[skill_name].secondary_tools = tools

    def build_tools_definition(self, activated_skills: set[str] | None = None) -> list[dict[str, Any]]:
        """
        构建 OpenAI tools 定义，支持动态二级工具加载

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
                                "description": "技能名称，如 'document-retrieval' 或其他已激活技能"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "references 目录下的相对文件路径，如 'references/评估/个人评估/MBTI.md'。注意：这个路径应该从你调用的技能的 SKILL.md 中获取。"
                            },
                            "lines": {
                                "type": "string",
                                "description": "可选：指定行范围，格式如 '100-200' 表示读取第100到200行。不指定则读取整个文件。"
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

        # 添加 form_memory 工具
        tools.append({
            "type": "function",
            "function": {
                "name": "form_memory",
                "description": "当你认为当前对话完成一个阶段，或者用户表示结束或需要总结时，调用此工具形成记忆",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "触发记忆形成的原因"
                        }
                    }
                }
            }
        })

        return tools

    def get_skill_content(self, skill_name: str) -> str:
        """
        获取技能内容

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
        获取技能完整信息

        Args:
            skill_name: 技能名称

        Returns:
            SkillInfo 对象，如果技能不存在则返回 None
        """
        return self.available_skills.get(skill_name)

    def read_reference(self, skill_name: str, file_path: str, lines: str = "") -> str:
        """
        读取技能目录下的 references 文件内容

        Args:
            skill_name: 技能名称
            file_path: references 目录下的相对文件路径
            lines: 可选行范围，格式如 "100-200" 表示读取第100到200行

        Returns:
            文件内容字符串，如果文件不存在则返回错误信息
        """
        skill_info = self.available_skills.get(skill_name)
        if skill_info is None or skill_info.path is None:
            return f"错误：技能 '{skill_name}' 不存在"

        # 构建完整的文件路径
        skill_dir = skill_info.path.parent
        reference_file = skill_dir / file_path

        # 检查文件是否存在
        if not reference_file.exists():
            # 尝试列出可用的文件
            refs_dir = skill_dir / "references"
            if refs_dir.exists():
                available_files = self._list_reference_files(refs_dir, "")
                hint = f"\n\n可用的 reference 文件:\n{available_files}"
            else:
                hint = f"\n\n该技能没有 references 目录"
            return f"错误：文件 '{file_path}' 不存在{hint}"

        try:
            content = reference_file.read_text(encoding="utf-8")

            # 处理行范围参数
            if lines:
                try:
                    # 解析行范围，格式如 "100-200"
                    if "-" in lines:
                        start_str, end_str = lines.split("-", 1)
                        start = int(start_str.strip()) - 1  # 转为0-based索引
                        end = int(end_str.strip())
                        lines_list = content.splitlines()
                        if start < 0:
                            start = 0
                        if end > len(lines_list):
                            end = len(lines_list)
                        if start < len(lines_list):
                            selected_lines = lines_list[start:end]
                            content = "\n".join(selected_lines)
                            content = f"[行 {start+1}-{end}]\n\n{content}"
                        else:
                            content = f"错误：起始行号 {start+1} 超出文件总行数 {len(lines_list)}"
                except (ValueError, IndexError):
                    return f"错误：行范围格式无效，应为 '起始-结束' 格式，如 '100-200'"

            return content
        except Exception as e:
            return f"错误：读取文件失败 - {e}"

    def _list_reference_files(self, dir_path: Path, prefix: str = "") -> str:
        """
        递归列出 references 目录下的所有文件

        Args:
            dir_path: 目录路径
            prefix: 路径前缀

        Returns:
            文件列表字符串
        """
        lines = []
        for item in sorted(dir_path.iterdir()):
            if item.is_dir():
                lines.append(self._list_reference_files(item, f"{prefix}{item.name}/"))
            else:
                lines.append(f"  - {prefix}{item.name}")
        return "\n".join(lines)
