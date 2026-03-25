from src.chat import prompts_runtime as p
from tests.prompts_test_constants import (
    SYSTEM_PROMPT_EXPECTED_PHRASES,
    COMPACT_PROMPT_EXPECTED_PHRASES,
)


def test_runtime_prompt_constants_exist():
    required = [
        "SYSTEM_PROMPT_TEMPLATE",
        "COMPACT_PROMPT_TEMPLATE",
        "MEMORY_PROMPT_TEMPLATE",
        "TITLE_PROMPT_TEMPLATE",
        "DOC_SUMMARY_SYSTEM_PROMPT",
        "DOC_SUMMARY_USER_PROMPT_TEMPLATE",
        "FORM_MEMORY_PROMPT_TEMPLATE",
        "READ_REFERENCE_TOOL_DESCRIPTION",
    ]
    for name in required:
        assert hasattr(p, name)


def test_system_prompt_contains_expected_phrases():
    """验证 SYSTEM_PROMPT_TEMPLATE 包含预期的关键短语"""
    for phrase in SYSTEM_PROMPT_EXPECTED_PHRASES:
        assert phrase in p.SYSTEM_PROMPT_TEMPLATE, (
            f"SYSTEM_PROMPT_TEMPLATE 缺少预期短语: {phrase}"
        )


def test_no_new_inline_prompt_templates_in_runtime_code():
    # 可在后续实现为静态扫描测试：关键目录不应新增三引号提示词常量
    assert True


def test_compact_prompt_contains_expected_phrases():
    """验证 COMPACT_PROMPT_TEMPLATE 包含预期的关键短语"""
    for phrase in COMPACT_PROMPT_EXPECTED_PHRASES:
        assert phrase in p.COMPACT_PROMPT_TEMPLATE, (
            f"COMPACT_PROMPT_TEMPLATE 缺少预期短语: {phrase}"
        )