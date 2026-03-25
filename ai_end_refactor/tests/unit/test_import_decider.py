"""import_decider 测试"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_should_run_auto_import_when_skills_need_import(monkeypatch):
    """测试当 skills 需要导入时返回 True"""
    from src.api.import_decider import should_run_auto_import

    monkeypatch.setattr("src.api.import_decider.needs_skill_import", AsyncMock(return_value=True))
    monkeypatch.setattr("src.api.import_decider.needs_document_import", AsyncMock(return_value=False))

    assert await should_run_auto_import() is True


@pytest.mark.asyncio
async def test_should_run_auto_import_when_documents_need_import(monkeypatch):
    """测试当 documents 需要导入时返回 True"""
    from src.api.import_decider import should_run_auto_import

    monkeypatch.setattr("src.api.import_decider.needs_skill_import", AsyncMock(return_value=False))
    monkeypatch.setattr("src.api.import_decider.needs_document_import", AsyncMock(return_value=True))

    assert await should_run_auto_import() is True


@pytest.mark.asyncio
async def test_should_skip_auto_import_when_all_datasets_complete(monkeypatch):
    """测试当所有数据集都完整时返回 False"""
    from src.api.import_decider import should_run_auto_import

    monkeypatch.setattr("src.api.import_decider.needs_skill_import", AsyncMock(return_value=False))
    monkeypatch.setattr("src.api.import_decider.needs_document_import", AsyncMock(return_value=False))

    assert await should_run_auto_import() is False


@pytest.mark.asyncio
async def test_should_run_auto_import_checks_only_two_datasets(monkeypatch):
    """测试自动导入检查仅针对 skills 和 documents 两个数据集"""
    from src.api.import_decider import should_run_auto_import

    call_count = {"skill": 0, "document": 0}

    async def mock_skill():
        call_count["skill"] += 1
        return False

    async def mock_document():
        call_count["document"] += 1
        return False

    monkeypatch.setattr("src.api.import_decider.needs_skill_import", mock_skill)
    monkeypatch.setattr("src.api.import_decider.needs_document_import", mock_document)

    await should_run_auto_import()

    assert call_count["skill"] == 1
    assert call_count["document"] == 1
