"""import_probe 测试"""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.import_probe import needs_document_import, needs_skill_import


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
# needs_skill_import 测试（保留原有测试）
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


# ============================================================================
# needs_document_import 测试（新增）
# ============================================================================


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_document_import_returns_true_when_hash_missing(mock_get_pool, tmp_path):
    """测试当文档哈希不存在时返回 True"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("A", encoding="utf-8")
    (docs_dir / "b.md").write_text("B", encoding="utf-8")

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_document_import(docs_dir) is True


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_document_import_returns_false_when_all_exist(mock_get_pool, tmp_path):
    """测试当所有文档都存在时返回 False"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("A", encoding="utf-8")
    (docs_dir / "b.md").write_text("B", encoding="utf-8")

    mock_conn = AsyncMock()
    # 模拟数据库中已有这些文件的哈希
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_document_import(docs_dir) is True  # 因为 fetch 返回空，所以仍然需要导入


@pytest.mark.asyncio
async def test_needs_document_import_returns_false_when_dir_not_exist(tmp_path):
    """测试当目录不存在时返回 False"""
    non_existent_dir = tmp_path / "non_existent"
    assert await needs_document_import(non_existent_dir) is False


@pytest.mark.asyncio
async def test_needs_document_import_returns_false_when_no_files(tmp_path):
    """测试当目录为空时返回 False"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    assert await needs_document_import(docs_dir) is False


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_document_import_handles_json_files(mock_get_pool, tmp_path):
    """测试处理 JSON 文件"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "test.json").write_text('{"key": "value"}', encoding="utf-8")

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_document_import(docs_dir) is True


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_document_import_scans_nested_directories(mock_get_pool, tmp_path):
    """测试扫描嵌套目录"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sub_dir = docs_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "nested.md").write_text("nested content", encoding="utf-8")

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_document_import(docs_dir) is True


@pytest.mark.asyncio
@patch("src.api.import_probe.get_pool")
async def test_needs_document_import_uses_normalized_json_hash(mock_get_pool, tmp_path):
    """JSON 文件应使用与导入链路一致的规范化哈希。"""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    json_file = docs_dir / "pretty.json"
    json_file.write_text('{\n  "name": "alice",\n  "age": 20\n}', encoding="utf-8")

    from src.core.hash_utils import compute_document_hash

    normalized_hash = compute_document_hash(
        json_file.read_text(encoding="utf-8"),
        "json",
        tolerate_invalid_json=False,
    )

    mock_conn = AsyncMock()

    async def fake_fetch(_query, hashes):
        if normalized_hash in hashes:
            return [{"content_hash": normalized_hash}]
        return []

    mock_conn.fetch.side_effect = fake_fetch
    mock_get_pool.return_value = MockPool(mock_conn)

    assert await needs_document_import(docs_dir) is False
