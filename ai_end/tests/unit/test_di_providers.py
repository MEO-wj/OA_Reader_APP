"""TDD: provider 便捷访问入口单元测试。"""

import pytest
from unittest.mock import Mock, patch

from src.core.skill_adapter import SkillBackend


class TestDIProviders:
    """providers.py 测试套件。"""

    def test_get_skill_system_uses_singleton_for_default_filesystem_backend(self):
        """默认文件系统技能系统应复用 singleton provider。"""
        from src.di import providers

        fake_container = Mock()
        fake_container.skill_system.return_value = "singleton-skill-system"

        with patch.object(providers, "get_container", return_value=fake_container):
            result = providers.get_skill_system()

        assert result == "singleton-skill-system"
        fake_container.skill_system.assert_called_once_with()
        fake_container.skill_system_factory.assert_not_called()

    def test_get_skill_system_uses_factory_for_database_backend(self):
        """数据库后端应显式走 factory provider。"""
        from src.di import providers

        fake_container = Mock()
        fake_container.skill_system_factory.return_value = "db-skill-system"

        with patch.object(providers, "get_container", return_value=fake_container):
            result = providers.get_skill_system(backend=SkillBackend.DATABASE)

        assert result == "db-skill-system"
        fake_container.skill_system_factory.assert_called_once_with(
            backend=SkillBackend.DATABASE,
            skills_dir="./skills",
        )
        fake_container.skill_system.assert_not_called()

    def test_get_skill_system_uses_factory_for_custom_filesystem_dir(self):
        """自定义 skills_dir 的文件系统后端应显式走 factory provider。"""
        from src.di import providers

        fake_container = Mock()
        fake_container.skill_system_factory.return_value = "custom-fs-skill-system"

        with patch.object(providers, "get_container", return_value=fake_container):
            result = providers.get_skill_system(
                backend=SkillBackend.FILESYSTEM,
                skills_dir="/tmp/custom-skills",
            )

        assert result == "custom-fs-skill-system"
        fake_container.skill_system_factory.assert_called_once_with(
            backend=SkillBackend.FILESYSTEM,
            skills_dir="/tmp/custom-skills",
        )
        fake_container.skill_system.assert_not_called()

    def test_get_skill_system_rejects_unsupported_backend(self):
        """未知 backend 不应隐式降级到文件系统实现。"""
        from src.di import providers

        with pytest.raises(ValueError, match="Unsupported skill backend"):
            providers.get_skill_system(backend="unsupported")  # type: ignore[arg-type]
