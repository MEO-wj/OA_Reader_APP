"""
技能解析器 - 从 SKILL.md 文件提取元数据和内容

TDD GREEN 阶段：编写最小代码通过测试
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillInfo:
    """技能信息数据类"""
    name: str
    description: str
    content: str
    verification_token: str
    path: Path | None = None
    secondary_tools: list[dict[str, Any]] = field(default_factory=list)  # 二级工具定义
    references_dir: Path | None = None  # 参考资料目录路径
    metadata: dict[str, Any] = field(default_factory=dict)  # front matter 原始元数据


class SkillParser:
    """解析 SKILL.md 文件，提取 YAML front matter 和内容"""

    # YAML front matter 的正则表达式
    YAML_PATTERN = re.compile(r'^---\n(.*?)\n---', re.DOTALL)

    def parse(self, content: str, filename: str = "") -> SkillInfo:
        """
        解析技能内容

        Args:
            content: SKILL.md 文件内容
            filename: 文件名（用于无 front matter 时的默认 name）

        Returns:
            SkillInfo 对象
        """
        yaml_match = self.YAML_PATTERN.match(content)

        if yaml_match:
            return self._parse_with_yaml(yaml_match, content)
        else:
            return self._parse_without_yaml(content, filename)

    def _parse_with_yaml(self, yaml_match, content: str) -> SkillInfo:
        """解析包含 YAML front matter 的内容"""
        front_matter_text = yaml_match.group(1)
        metadata = self._parse_simple_yaml(front_matter_text)

        skill_content = content[yaml_match.end():].strip()

        return SkillInfo(
            name=metadata.get('name', ''),
            description=metadata.get('description', ''),
            content=skill_content,
            verification_token=metadata.get('verification_token', ''),
            path=None,
            metadata=metadata,
        )

    def _parse_without_yaml(self, content: str, filename: str) -> SkillInfo:
        """解析无 YAML front matter 的内容"""
        description = content.replace('\n', ' ')[:200]

        return SkillInfo(
            name=filename,
            description=description,
            content=content,
            verification_token='',
            path=None,
            metadata={},
        )

    def _parse_simple_yaml(self, yaml_text: str) -> dict:
        """简单的 YAML 解析器（仅支持 key: value 格式）"""
        metadata = {}
        for line in yaml_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
        return metadata

    def parse_file(self, file_path: Path) -> SkillInfo:
        """
        从文件路径解析技能

        Args:
            file_path: SKILL.md 文件路径

        Returns:
            SkillInfo 对象，path 字段设置为文件路径
        """
        content = file_path.read_text(encoding='utf-8')
        filename = file_path.parent.name

        skill_info = self.parse(content, filename)
        skill_info.path = file_path
        skill_info.references_dir = file_path.parent / "references"

        # 解析 TOOLS.md（如果存在）
        tools_path = file_path.parent / "TOOLS.md"
        if tools_path.exists():
            skill_info.secondary_tools = self._parse_tools_file(tools_path)

        return skill_info

    def _parse_tools_file(self, tools_path: Path) -> list[dict[str, Any]]:
        """
        解析 TOOLS.md 文件，提取二级工具定义

        Args:
            tools_path: TOOLS.md 文件路径

        Returns:
            工具定义列表，每个工具包含 name, description, parameters, handler
        """
        content = tools_path.read_text(encoding='utf-8')
        tools = []

        # 按分隔符分割多个工具定义
        tool_blocks = re.split(r'\n---+\n', content)

        for block in tool_blocks:
            block = block.strip()
            if not block:
                continue

            tool_def = self._parse_tool_block(block)
            if tool_def:
                tools.append(tool_def)

        return tools

    def _parse_tool_block(self, block: str) -> dict[str, Any] | None:
        """
        解析单个工具定义块

        Args:
            block: 工具定义文本块

        Returns:
            工具定义字典，包含 name, description, parameters, handler
        """
        lines = block.split('\n')
        tool_def = {
            "name": "",
            "description": "",
            "parameters": {},
            "handler": ""
        }

        current_section = None
        param_lines = []

        for line in lines:
            # 检测章节标题
            if line.startswith('## '):
                current_section = line[3:].strip().lower()
                continue

            # 跳过空行
            if not line.strip():
                continue

            # 解析各个章节
            if current_section == "工具名称":
                tool_def["name"] = line.strip()
            elif current_section == "功能描述":
                tool_def["description"] += line.strip() + " "
            elif current_section == "调用参数":
                # 收集参数行，稍后解析
                param_lines.append(line)
            elif current_section == "处理函数":
                tool_def["handler"] = line.strip()

        # 清理描述
        tool_def["description"] = tool_def["description"].strip()

        # 解析参数
        tool_def["parameters"] = self._parse_parameters(param_lines)

        # 验证必需字段
        if not tool_def["name"] or not tool_def["handler"]:
            return None

        return tool_def

    def _parse_parameters(self, param_lines: list[str]) -> dict[str, Any]:
        """
        解析参数定义

        Args:
            param_lines: 参数文本行列表

        Returns:
            JSON Schema 格式的参数定义
        """
        properties = {}
        required = []

        for line in param_lines:
            line = line.strip()
            if not line or line.startswith('```'):
                continue

            # 解析参数行格式：- 参数名 (类型): 描述
            param_match = re.match(r'-\s*(\w+)\s*\((\w+)\)\s*:\s*(.+)', line)
            if param_match:
                param_name = param_match.group(1)
                param_type = param_match.group(2)
                param_desc = param_match.group(3)

                # 映射类型到 JSON Schema
                type_mapping = {
                    "str": "string",
                    "int": "integer",
                    "float": "number",
                    "bool": "boolean",
                    "list": "array",
                    "dict": "object"
                }

                properties[param_name] = {
                    "type": type_mapping.get(param_type, "string"),
                    "description": param_desc
                }

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
