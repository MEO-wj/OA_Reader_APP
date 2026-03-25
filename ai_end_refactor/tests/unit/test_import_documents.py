"""import_documents 脚本测试。"""

import inspect
from pathlib import Path

import pytest

from scripts.import_documents import filter_files_not_in_db


def test_generate_summary_prompt_is_centralized():
    """验证 generate_summary 函数使用集中化的提示词常量"""
    from scripts import import_documents

    # 获取 generate_summary 函数的源代码
    source = inspect.getsource(import_documents.generate_summary)

    # 验证函数中是否使用了 DOC_SUMMARY_SYSTEM_PROMPT 和 DOC_SUMMARY_USER_PROMPT_TEMPLATE
    assert "DOC_SUMMARY_SYSTEM_PROMPT" in source, \
        "generate_summary 应该使用 DOC_SUMMARY_SYSTEM_PROMPT"
    assert "DOC_SUMMARY_USER_PROMPT_TEMPLATE" in source, \
        "generate_summary 应该使用 DOC_SUMMARY_USER_PROMPT_TEMPLATE"


@pytest.mark.asyncio
async def test_filter_files_not_in_db_keeps_invalid_json_file(tmp_path: Path):
    """遇到非法 JSON 时不应中断整批过滤，应保留该文件后续逐个处理。"""
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{ invalid json", encoding="utf-8")

    result = await filter_files_not_in_db([bad_json])

    assert result == [bad_json]
