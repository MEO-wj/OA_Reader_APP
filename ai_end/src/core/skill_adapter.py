"""统一技能系统适配层。"""

from __future__ import annotations

import inspect

from enum import Enum
from typing import Any

from src.core.db_skill_system import DbSkillSystem
from src.core.skill_system import SkillSystem


class SkillBackend(Enum):
    """技能后端类型。"""

    DATABASE = "database"
    FILESYSTEM = "filesystem"


class SkillAdapter:
    """统一封装文件系统/数据库技能后端。"""

    def __init__(self, backend: Any, data_source: str):
        self._backend = backend
        self.data_source = data_source
        self.available_skills = getattr(backend, "available_skills", {})

    @property
    def backend(self) -> Any:
        """暴露底层后端，便于兼容现有调用与测试。"""
        return self._backend

    @classmethod
    def create(cls, backend: SkillBackend, **kwargs: Any) -> "SkillAdapter":
        """根据后端类型创建统一适配器。"""
        if backend == SkillBackend.DATABASE:
            return cls(DbSkillSystem(), "database")

        skills_dir = kwargs.get("skills_dir", "./skills")
        return cls(SkillSystem(skills_dir), "filesystem")

    async def load_skills(self) -> None:
        """按需加载技能。"""
        load_method = getattr(self._backend, "_load_skills_from_db", None)
        if load_method is not None:
            await load_method()
        self.available_skills = getattr(self._backend, "available_skills", {})

    def get_skill_content(self, skill_name: str) -> str:
        return self._backend.get_skill_content(skill_name)

    def get_skill_info(self, skill_name: str) -> Any:
        return self._backend.get_skill_info(skill_name)

    def build_tools_definition(
        self, activated_skills: set[str] | None = None, *, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        build_fn = self._backend.build_tools_definition
        sig = inspect.signature(build_fn)
        if "user_id" in sig.parameters:
            return build_fn(activated_skills, user_id=user_id)
        return build_fn(activated_skills)

    async def read_reference(
        self, skill_name: str, file_path: str, lines: str = ""
    ) -> str:
        """统一异步读取 reference。"""
        read_method = self._backend.read_reference
        from inspect import iscoroutinefunction

        if iscoroutinefunction(read_method):
            return await read_method(skill_name, file_path, lines)

        return read_method(skill_name, file_path, lines)
