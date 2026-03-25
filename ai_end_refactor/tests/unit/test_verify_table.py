"""verify_table 脚本测试。"""

import inspect

import pytest

from migrations import verify_table


def test_verify_table_targets_documents_schema():
    """verify_table 应校验 documents 表，不应再引用 policies。"""
    source = inspect.getsource(verify_table.verify_table).lower()

    assert "documents" in source
    assert "policies" not in source


@pytest.mark.asyncio
async def test_verify_table_returns_false_when_connect_fails(monkeypatch):
    """数据库连接失败时应返回 False，且不因 finally 引发二次异常。"""

    async def fake_connect(**kwargs):
        raise RuntimeError("connect failed")

    monkeypatch.setattr(verify_table.asyncpg, "connect", fake_connect)

    success = await verify_table.verify_table()

    assert success is False
