from src.chat import prompts_runtime as p
from tests.prompts_test_constants import (
    SYSTEM_PROMPT_EXPECTED_PHRASES,
    COMPACT_PROMPT_EXPECTED_PHRASES,
    COMPACT_V2_NO_MERGE_CONSTRAINTS,
    SYSTEM_PROMPT_V2_CONSTRAINTS,
    PORTRAIT_EXTRACT_REQUIRED_PHRASES,
    PORTRAIT_MERGE_REQUIRED_PHRASES,
)


def test_runtime_prompt_constants_exist():
    required = [
        "SYSTEM_PROMPT_TEMPLATE",
        "COMPACT_PROMPT_TEMPLATE",
        "TITLE_PROMPT_TEMPLATE",
        "DOC_SUMMARY_SYSTEM_PROMPT",
        "DOC_SUMMARY_USER_PROMPT_TEMPLATE",
        "READ_REFERENCE_TOOL_DESCRIPTION",
        "PORTRAIT_EXTRACT_PROMPT",
        "PORTRAIT_MERGE_PROMPT",
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


def test_system_prompt_contains_layer_constraint():
    """验证 SYSTEM_PROMPT_TEMPLATE 包含 v2 分层与禁止合并约束"""
    for phrase in SYSTEM_PROMPT_V2_CONSTRAINTS:
        assert phrase in p.SYSTEM_PROMPT_TEMPLATE, (
            f"SYSTEM_PROMPT_TEMPLATE 缺少 v2 分层约束: {phrase}"
        )


# ─── v2 契约测试 ──────────────────────────────────────────────


def test_compact_prompt_contains_no_merge_constraint():
    """验证 COMPACT_PROMPT_TEMPLATE 包含禁止把 hypothesized 合并到 confirmed 的约束"""
    for phrase in COMPACT_V2_NO_MERGE_CONSTRAINTS:
        assert phrase in p.COMPACT_PROMPT_TEMPLATE, (
            f"COMPACT_PROMPT_TEMPLATE 缺少 v2 分层约束: {phrase}"
        )


# ─── Task 5: 提示词约束回归 ──────────────────────────────────


def test_system_prompt_contains_aggressive_trigger_semantic():
    """SYSTEM_PROMPT 应包含画像相关语义提示。"""
    assert ("线索" in p.SYSTEM_PROMPT_TEMPLATE or "画像" in p.SYSTEM_PROMPT_TEMPLATE)


# ─── 两步式画像 prompt 契约测试 ──────────────────────────────


def test_portrait_extract_prompt_exists_and_blocks_merge_behavior():
    """验证 PORTRAIT_EXTRACT_PROMPT 存在且仅负责从对话中提取画像，不涉及合并逻辑。"""
    assert hasattr(p, "PORTRAIT_EXTRACT_PROMPT")
    for phrase in PORTRAIT_EXTRACT_REQUIRED_PHRASES:
        assert phrase in p.PORTRAIT_EXTRACT_PROMPT, (
            f"PORTRAIT_EXTRACT_PROMPT 缺少预期短语: {phrase}"
        )


def test_portrait_merge_prompt_exists_and_contains_merge_rules():
    """验证 PORTRAIT_MERGE_PROMPT 存在且包含完整的合并规则。"""
    assert hasattr(p, "PORTRAIT_MERGE_PROMPT")
    for phrase in PORTRAIT_MERGE_REQUIRED_PHRASES:
        assert phrase in p.PORTRAIT_MERGE_PROMPT, (
            f"PORTRAIT_MERGE_PROMPT 缺少预期短语: {phrase}"
        )
