"""TDD: 统一技能适配层单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSkillAdapter:
    """SkillAdapter 测试套件。"""

    def test_create_from_database_backend(self):
        """应支持创建数据库后端适配器。"""
        from src.core.skill_adapter import SkillAdapter, SkillBackend

        with patch("src.core.skill_adapter.DbSkillSystem") as mock_backend:
            adapter = SkillAdapter.create(SkillBackend.DATABASE)

        assert adapter is not None
        assert adapter.data_source == "database"
        assert adapter.backend is mock_backend.return_value

    def test_create_from_filesystem_backend(self, tmp_path):
        """应支持创建文件系统后端适配器。"""
        from src.core.skill_adapter import SkillAdapter, SkillBackend

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        adapter = SkillAdapter.create(SkillBackend.FILESYSTEM, skills_dir=str(skills_dir))

        assert adapter is not None
        assert adapter.data_source == "filesystem"
        assert adapter.backend is not None

    @pytest.mark.asyncio
    async def test_load_skills_from_database_backend(self):
        """数据库后端应可通过统一接口异步加载技能。"""
        from src.core.skill_adapter import SkillAdapter, SkillBackend

        mock_backend = MagicMock()
        mock_backend.available_skills = {"test-skill": object()}
        mock_backend._load_skills_from_db = AsyncMock()

        with patch("src.core.skill_adapter.DbSkillSystem", return_value=mock_backend):
            adapter = SkillAdapter.create(SkillBackend.DATABASE)
            await adapter.load_skills()

        mock_backend._load_skills_from_db.assert_awaited_once()
        assert adapter.available_skills == mock_backend.available_skills

    @pytest.mark.asyncio
    async def test_read_reference_async_with_sync_backend(self, tmp_path):
        """同步后端应可通过异步包装读取 reference。"""
        from src.core.skill_adapter import SkillAdapter, SkillBackend

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        adapter = SkillAdapter.create(SkillBackend.FILESYSTEM, skills_dir=str(skills_dir))

        with patch.object(
            adapter.backend,
            "read_reference",
            return_value="reference content",
        ) as mock_read:
            content = await adapter.read_reference("demo", "references/a.md")

        mock_read.assert_called_once_with("demo", "references/a.md", "")
        assert content == "reference content"

    def test_build_tools_passes_user_id_via_kwargs(self):
        """build_tools_definition 应通过 kwargs 透传 user_id，不依赖 inspect.signature。"""
        from src.core.skill_adapter import SkillAdapter, SkillBackend

        mock_backend = MagicMock()
        mock_backend.build_tools_definition.return_value = [{"type": "function", "function": {"name": "test"}}]

        with patch("src.core.skill_adapter.DbSkillSystem", return_value=mock_backend):
            adapter = SkillAdapter.create(SkillBackend.DATABASE)
            result = adapter.build_tools_definition(activated_skills=None, user_id="u1")

        mock_backend.build_tools_definition.assert_called_once()
        call_kwargs = mock_backend.build_tools_definition.call_args
        # user_id 应通过 kwargs 透传
        assert call_kwargs.kwargs.get("user_id") == "u1"
        assert result == [{"type": "function", "function": {"name": "test"}}]

    def test_build_tools_with_filesystem_backend_ignores_user_id(self, tmp_path):
        """文件系统后端不支持 user_id 时，透传不应报错。"""
        from src.core.skill_adapter import SkillAdapter, SkillBackend

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        adapter = SkillAdapter.create(SkillBackend.FILESYSTEM, skills_dir=str(skills_dir))
        # 文件系统后端不报错即可
        result = adapter.build_tools_definition(activated_skills=None, user_id="u_ignored")
        assert isinstance(result, list)

