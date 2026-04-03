"""import_probe 测试"""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.import_probe import needs_skill_import


class AsyncContextManager:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class MockPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return AsyncContextManager(self._conn)


# ============================================================================
# needs_skill_import 测试
# ============================================================================


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_skill_import_returns_true_when_db_missing_skill(mock_get_pool, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\n# Demo",
        encoding="utf-8",
    )

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_skill_import(skills_dir) is True


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_skill_import_returns_false_when_skill_matches(mock_get_pool, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir()
    content = "---\nname: demo\ndescription: d\n---\n\n# Demo"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {
            "name": "demo",
            "content": content,
            "tools": None,
            "file_path": None,
            "ref_content": None,
        }
    ]
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_skill_import(skills_dir) is False


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_skill_import_is_order_insensitive_for_references(mock_get_pool, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "demo"
    skill_dir.mkdir()
    references_dir = skill_dir / "references"
    references_dir.mkdir()

    content = "---\nname: demo\ndescription: d\n---\n\n# Demo"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    (references_dir / "a.md").write_text("A", encoding="utf-8")
    (references_dir / "b.md").write_text("B", encoding="utf-8")

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {
            "name": "demo",
            "content": content,
            "tools": None,
            "file_path": "b.md",
            "ref_content": "B",
        },
        {
            "name": "demo",
            "content": content,
            "tools": None,
            "file_path": "a.md",
            "ref_content": "A",
        },
    ]
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_skill_import(skills_dir) is False
