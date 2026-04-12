"""
测试 src.core.todolist_handler - 任务步骤检查点
"""
import json

import pytest
from unittest.mock import Mock

from src.core.todolist_handler import check_step, _is_valid_skip_reason


class TestIsValidSkipReason:
    """测试跳过理由校验"""

    def test_empty_reason_is_invalid(self):
        assert _is_valid_skip_reason("") is False

    def test_none_reason_is_invalid(self):
        assert _is_valid_skip_reason(None) is False

    def test_whitespace_only_is_invalid(self):
        assert _is_valid_skip_reason("   ") is False

    def test_short_reason_under_5_chars_is_invalid(self):
        assert _is_valid_skip_reason("无") is False

    def test_reason_exactly_3_chars_is_invalid(self):
        assert _is_valid_skip_reason("不需要") is False  # 3个字 < 5

    def test_long_reason_is_valid(self):
        assert _is_valid_skip_reason("用户只是简单问候无需记忆") is True

    def test_reason_5_chars_is_valid(self):
        assert _is_valid_skip_reason("12345") is True


class TestCheckStepStep1:
    """测试步骤1（判断是否保存记忆）"""

    @pytest.mark.asyncio
    async def test_step1_done_passes(self):
        result = await check_step(step=1, status="done")
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_valid_reason_passes(self):
        result = await check_step(step=1, status="skip", reason="用户只是打招呼，没有提供任何个人信息")
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_empty_reason_rejected(self):
        result = await check_step(step=1, status="skip", reason="")
        assert result["success"] is False
        assert "error" in result
        assert "步骤1" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_short_reason_rejected(self):
        result = await check_step(step=1, status="skip", reason="无")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_step1_start_passes(self):
        result = await check_step(step=1, status="start")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_step1_done_without_reason_passes(self):
        result = await check_step(step=1, status="done")
        assert result["success"] is True


class TestCheckStepStep2:
    """测试步骤2（判断是否需要查询文章）"""

    @pytest.mark.asyncio
    async def test_step2_done_passes(self):
        result = await check_step(step=2, status="done")
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_valid_reason_passes(self):
        result = await check_step(step=2, status="skip", reason="用户问题与OA文章无关，不需要查询")
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_empty_reason_rejected(self):
        result = await check_step(step=2, status="skip", reason="")
        assert result["success"] is False
        assert "error" in result
        assert "步骤2" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_short_reason_rejected(self):
        result = await check_step(step=2, status="skip", reason="跳过")
        assert result["success"] is False


class TestCheckStepStep3:
    """测试步骤3（整理并总结回答）"""

    @pytest.mark.asyncio
    async def test_step3_always_passes(self):
        result = await check_step(step=3, status="done")
        assert result["success"] is True
        assert "最终回答" in result["message"]

    @pytest.mark.asyncio
    async def test_step3_with_skip_also_passes(self):
        result = await check_step(step=3, status="skip")
        assert result["success"] is True


class TestCheckStepEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_invalid_step_returns_generic_success(self):
        result = await check_step(step=99, status="done")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reason_with_only_whitespace_treated_as_empty(self):
        result = await check_step(step=1, status="skip", reason="   ")
        assert result["success"] is False


class TestTodolistCheckIntegration:
    """测试 todolist_check 通过 handle_tool_calls 完整调用链"""

    @pytest.fixture
    def todolist_skill_system(self):
        """构建包含 todolist 技能及其二级工具的 mock skill_system"""
        from src.core.skill_parser import SkillInfo

        mock = Mock()
        mock.available_skills = {
            "todolist": SkillInfo(
                name="todolist",
                description="任务执行框架",
                content="",
                verification_token="TODOLIST-FRAMEWORK-2026",
            )
        }
        mock.available_skills["todolist"].secondary_tools = [
            {"name": "todolist_check", "handler": "todolist_handler.check_step"}
        ]
        return mock

    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_through_handle_tool_calls(self, todolist_skill_system):
        """todolist_check(step=1, status=done) 应通过 handle_tool_calls 正确返回成功"""
        from src.chat.handlers import handle_tool_calls

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_1"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is True
        assert "步骤2" in data["message"]

    @pytest.mark.asyncio
    async def test_todolist_check_step1_skip_invalid_rejected_through_handle_tool_calls(self, todolist_skill_system):
        """todolist_check(step=1, status=skip, reason="无") 应被拒绝"""
        from src.chat.handlers import handle_tool_calls

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "skip", "reason": "无"}'
        mock_tool_call.id = "call_tl_2"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is False
        assert "error" in data

    @pytest.mark.asyncio
    async def test_todolist_check_step2_skip_valid_through_handle_tool_calls(self, todolist_skill_system):
        """todolist_check(step=2, status=skip, reason=valid) 应通过"""
        from src.chat.handlers import handle_tool_calls

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 2, "status": "skip", "reason": "用户问题与OA文章无关，不需要查询"}'
        mock_tool_call.id = "call_tl_3"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is True
        assert "步骤3" in data["message"]
