"""
工具激活策略。
"""

from typing import AbstractSet, Mapping

from src.core.skill_parser import SkillInfo


def _is_guidance_skill(skill_name: str, skill_info: SkillInfo | None) -> bool:
    """判断技能是否属于可开启 read_reference 的指导技能。

    仅基于 metadata 判定：
    - read_reference_parent 为 true（bool 或 string truthy）
    - skill_type == "guidance"
    """
    if skill_info is None:
        return False

    metadata = skill_info.metadata if isinstance(skill_info.metadata, dict) else {}

    # 判定方式1: read_reference_parent 标志
    parent_flag = metadata.get("read_reference_parent")
    if isinstance(parent_flag, str):
        if parent_flag.strip().lower() in {"1", "true", "yes", "on"}:
            return True
    elif bool(parent_flag):
        return True

    # 判定方式2: skill_type == "guidance"
    skill_type = metadata.get("skill_type")
    if isinstance(skill_type, str) and skill_type.strip().lower() == "guidance":
        return True

    return False


def should_enable_read_reference(
    activated_skills: AbstractSet[str],
    available_skills: Mapping[str, SkillInfo] | None = None,
) -> bool:
    """
    仅当指导技能已激活时启用 read_reference。
    """
    if not activated_skills:
        return False

    skills_map = available_skills or {}
    return any(_is_guidance_skill(name, skills_map.get(name)) for name in activated_skills)

