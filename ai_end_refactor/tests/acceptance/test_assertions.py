# tests/acceptance/test_assertions.py
from tests.acceptance.utils.assertions import AssertionHelper


def test_assert_tool_calls_match():
    """测试工具调用匹配"""
    actual = [{"name": "general-guidance", "arguments": {}}]
    expected = ["general-guidance"]

    passed, reason = AssertionHelper.assert_tool_calls(actual, expected)

    assert passed is True
    assert reason == ""


def test_assert_tool_calls_missing():
    """测试工具调用缺失"""
    actual = [{"name": "other-skill", "arguments": {}}]
    expected = ["general-guidance"]

    passed, reason = AssertionHelper.assert_tool_calls(actual, expected)

    assert passed is False
    assert "general-guidance" in reason


def test_assert_tool_calls_match_generic_skill():
    """测试通用技能名应该匹配"""
    actual = [{"name": "general-guidance", "arguments": {}}]
    expected = ["general-guidance"]
    passed, reason = AssertionHelper.assert_tool_calls(actual, expected)
    assert passed is True
    assert reason == ""


def test_assert_event_sequence():
    """测试事件序列验证"""
    events = ["start", "tool_call", "delta", "done"]
    expected = ["start", "delta", "done"]

    passed = AssertionHelper.assert_event_sequence(events, expected)

    assert passed is True


def test_assert_event_sequence_missing():
    """测试事件序列缺失"""
    events = ["start", "tool_call"]
    expected = ["start", "delta", "done"]

    passed = AssertionHelper.assert_event_sequence(events, expected)

    assert passed is False


def test_assert_response_contains_keywords():
    """测试响应关键词检查"""
    response = "根据你的大二现状，建议分三个阶段：第一阶段..."
    criteria = {"min_stages": 2}

    passed, note = AssertionHelper.assert_response_criteria(response, criteria)

    assert passed is True


def test_assert_response_insufficient_stages():
    """测试响应阶段不足"""
    response = "这是一个简单的回答"
    criteria = {"min_stages": 2}

    passed, note = AssertionHelper.assert_response_criteria(response, criteria)

    assert passed is False
    assert "阶段" in note


def test_evaluate_dimension_all_pass():
    """测试三维评分全部通过"""
    response = "建议分三个阶段：1. 第一步 2. 第二步"
    tool_calls = [{"name": "search_documents", "arguments": "{}", "result": "{}"}]
    skills_called = ["general-guidance"]
    criteria = {"expected_skills": ["general-guidance"]}

    result = AssertionHelper.evaluate_dimension(response, tool_calls, skills_called, criteria)

    assert result == {
        "tool_chain": "pass",
        "evidence_driven": "pass",
        "actionable": "pass",
    }


def test_evaluate_dimension_tool_chain_fail():
    """测试工具链评分失败"""
    response = "建议分三个阶段：1. 第一步 2. 第二步"
    tool_calls = [{"name": "other-tool", "arguments": "{}", "result": "{}"}]
    skills_called = ["other-skill"]
    criteria = {"expected_skills": ["general-guidance"]}

    result = AssertionHelper.evaluate_dimension(response, tool_calls, skills_called, criteria)

    assert result["tool_chain"].startswith("fail")
    assert result["actionable"] == "pass"


def test_evaluate_dimension_actionable_fail():
    """测试可执行性评分失败"""
    response = "这是一段没有结构的回答"
    tool_calls = []
    skills_called = []
    criteria = {}

    result = AssertionHelper.evaluate_dimension(response, tool_calls, skills_called, criteria)

    assert result["actionable"] == "fail"
