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
        result = await check_step(step=1, status="done", called_tools=["form_memory"])
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_valid_reason_passes(self):
        result = await check_step(step=1, status="skip", called_tools=[], reason="用户只是打招呼，没有提供任何个人信息")
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_empty_reason_rejected(self):
        result = await check_step(step=1, status="skip", called_tools=[], reason="")
        assert result["success"] is False
        assert "error" in result
        assert "步骤1" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_skip_with_short_reason_rejected(self):
        result = await check_step(step=1, status="skip", called_tools=[], reason="无")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_step1_start_passes(self):
        result = await check_step(step=1, status="start", called_tools=[])
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_step1_done_without_reason_passes(self):
        """status=done 时不需要 reason"""
        result = await check_step(step=1, status="done", called_tools=["form_memory"])
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_step1_done_without_form_memory_rejected(self):
        """status=done 但 called_tools 中无 form_memory 应被打回"""
        result = await check_step(step=1, status="done", called_tools=["todolist_check"])
        assert result["success"] is False
        assert "error" in result
        assert "form_memory" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_done_with_form_memory_passes(self):
        """status=done 且 called_tools 中有 form_memory 应通过"""
        result = await check_step(step=1, status="done", called_tools=["form_memory", "todolist_check"])
        assert result["success"] is True
        assert "步骤2" in result["message"]

    @pytest.mark.asyncio
    async def test_step1_done_with_empty_called_tools_rejected(self):
        """status=done 但 called_tools 为空列表应被打回"""
        result = await check_step(step=1, status="done", called_tools=[])
        assert result["success"] is False
        assert "form_memory" in result["error"]

    @pytest.mark.asyncio
    async def test_step1_done_with_reason_includes_reason_in_message(self):
        """status=done 且有 reason 时 message 应附带 reason"""
        result = await check_step(step=1, status="done", called_tools=["form_memory"], reason="用户分享了专业信息")
        assert result["success"] is True
        assert "备注" in result["message"]
        assert "用户分享了专业信息" in result["message"]


class TestCheckStepStep2:
    """测试步骤2（判断是否需要查询文章）"""

    @pytest.mark.asyncio
    async def test_step2_done_passes(self):
        result = await check_step(step=2, status="done", called_tools=["search_articles"])
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_valid_reason_passes(self):
        result = await check_step(step=2, status="skip", called_tools=[], reason="用户问题与OA文章无关，不需要查询")
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_empty_reason_rejected(self):
        result = await check_step(step=2, status="skip", called_tools=[], reason="")
        assert result["success"] is False
        assert "error" in result
        assert "步骤2" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_skip_with_short_reason_rejected(self):
        result = await check_step(step=2, status="skip", called_tools=[], reason="跳过")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_step2_done_without_search_tool_rejected(self):
        """status=done 但 called_tools 中无搜索工具应被打回"""
        result = await check_step(step=2, status="done", called_tools=["todolist_check"])
        assert result["success"] is False
        assert "error" in result
        assert "search_articles" in result["error"] or "grep_article" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_done_with_search_articles_passes(self):
        """status=done 且 called_tools 中有 search_articles 应通过"""
        result = await check_step(step=2, status="done", called_tools=["search_articles"])
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_done_with_grep_article_passes(self):
        """status=done 且 called_tools 中有 grep_article 应通过"""
        result = await check_step(step=2, status="done", called_tools=["grep_article"])
        assert result["success"] is True
        assert "步骤3" in result["message"]

    @pytest.mark.asyncio
    async def test_step2_done_with_empty_called_tools_rejected(self):
        """status=done 但 called_tools 为空列表应被打回"""
        result = await check_step(step=2, status="done", called_tools=[])
        assert result["success"] is False


class TestCheckStepStep3:
    """测试步骤3（整理并总结回答）"""

    @pytest.mark.asyncio
    async def test_step3_always_passes(self):
        result = await check_step(step=3, status="done", called_tools=[])
        assert result["success"] is True
        assert "最终回答" in result["message"]

    @pytest.mark.asyncio
    async def test_step3_with_skip_also_passes(self):
        result = await check_step(step=3, status="skip", called_tools=[])
        assert result["success"] is True


class TestValidateDoneActionDescription:
    """测试 _validate_done 的错误信息完全由 REQUIRED_TOOLS 驱动，不依赖外部传入的 action_desc。"""

    @pytest.mark.asyncio
    async def test_step1_error_contains_tool_name_without_action_desc(self):
        """步骤1 done 失败时错误信息应包含工具名（form_memory），无需硬编码 action_desc。"""
        result = await check_step(step=1, status="done", called_tools=[])
        assert result["success"] is False
        assert "form_memory" in result["error"]
        # 错误信息应包含"请先"或类似动作提示，引导 LLM 补救
        assert "请先" in result["error"] or "请" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_error_contains_tool_names_without_action_desc(self):
        """步骤2 done 失败时错误信息应包含搜索工具名。"""
        result = await check_step(step=2, status="done", called_tools=[])
        assert result["success"] is False
        # 至少应包含一个搜索工具名
        assert "search_articles" in result["error"] or "grep_article" in result["error"]
        assert "请先" in result["error"] or "请" in result["error"]


class TestCheckStepEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_invalid_step_returns_generic_success(self):
        result = await check_step(step=99, status="done", called_tools=[])
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reason_with_only_whitespace_treated_as_empty(self):
        result = await check_step(step=1, status="skip", called_tools=[], reason="   ")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_called_tools_none_triggers_defensive_check(self):
        """called_tools 为 None 时应打回而非抛出 TypeError"""
        result = await check_step(step=1, status="done", called_tools=None)
        assert result["success"] is False
        assert "内部错误" in result["error"]

    @pytest.mark.asyncio
    async def test_called_tools_string_triggers_defensive_check(self):
        """called_tools 为非 list 类型时应打回"""
        result = await check_step(step=1, status="done", called_tools="form_memory")
        assert result["success"] is False
        assert "内部错误" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self):
        result = await check_step(step=1, status="invalid", called_tools=[])
        assert result["success"] is False
        assert "status" in result["error"]

    @pytest.mark.asyncio
    async def test_step2_invalid_status_rejected(self):
        result = await check_step(step=2, status="oops", called_tools=[])
        assert result["success"] is False
        assert "status" in result["error"]


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
        """todolist_check(step=1, status=done) 在同一批有 form_memory 时应通过"""
        from src.chat.handlers import handle_tool_calls

        mock_form_memory = Mock()
        mock_form_memory.function.name = "form_memory"
        mock_form_memory.function.arguments = '{"reason": "test"}'
        mock_form_memory.id = "call_fm_0"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_1"

        result = await handle_tool_calls(
            [mock_form_memory, mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        done_data = json.loads(result[1]["content"])
        assert done_data["success"] is True
        assert "步骤2" in done_data["message"]

    @pytest.mark.asyncio
    async def test_todolist_check_step1_skip_invalid_rejected_through_handle_tool_calls(self, todolist_skill_system):
        """todolist_check(step=1, status=skip, reason="无") 应被拒绝"""
        from src.chat.handlers import handle_tool_calls

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "skip", "called_tools": [], "reason": "无"}'
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
        mock_tool_call.function.arguments = '{"step": 2, "status": "skip", "called_tools": [], "reason": "用户问题与OA文章无关，不需要查询"}'
        mock_tool_call.id = "call_tl_3"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is True
        assert "步骤3" in data["message"]

    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_without_form_memory_in_same_batch_rejected(self, todolist_skill_system):
        """同一批 tool_calls 中 done 但无 form_memory 应被打回"""
        from src.chat.handlers import handle_tool_calls

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_4"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        assert data["success"] is False
        assert "form_memory" in data["error"]

    @pytest.mark.asyncio
    async def test_todolist_check_step1_done_with_form_memory_in_same_batch_passes(self, todolist_skill_system):
        """同一批 tool_calls 中 form_memory + done 应通过"""
        from src.chat.handlers import handle_tool_calls

        mock_form_memory = Mock()
        mock_form_memory.function.name = "form_memory"
        mock_form_memory.function.arguments = '{"reason": "test"}'
        mock_form_memory.id = "call_fm_1"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_5"

        result = await handle_tool_calls(
            [mock_form_memory, mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        # form_memory 在无 user_id 时返回纯文本，不解析为 JSON
        assert "记忆" in result[0]["content"] or "登记" in result[0]["content"]

        done_data = json.loads(result[1]["content"])
        assert done_data["success"] is True
        assert "步骤2" in done_data["message"]

    @pytest.mark.asyncio
    async def test_todolist_check_forged_called_tools_overridden(self, todolist_skill_system):
        """LLM 在 called_tools 中伪造 form_memory，但实际未调用，系统注入应覆盖伪造值"""
        from src.chat.handlers import handle_tool_calls

        # LLM 尝试在参数中伪造 called_tools=["form_memory"]
        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done", "called_tools": ["form_memory"]}'
        mock_tool_call.id = "call_tl_forge"

        result = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
        )

        data = json.loads(result[0]["content"])
        # processed_tools 为空（没有实际调用 form_memory），系统注入覆盖伪造值
        assert data["success"] is False
        assert "form_memory" in data["error"]

    @pytest.mark.asyncio
    async def test_cross_batch_form_memory_detected_by_todolist_check(self, todolist_skill_system):
        """form_memory 在前一批次调用后，todolist_check 在后续批次应能检测到

        复现场景：LLM 先返回 form_memory（批次1），处理完后返回 todolist_check（批次2）。
        turn_tools 参数在批次间共享，使 todolist_check 能看到之前调用的 form_memory。
        """
        from src.chat.handlers import handle_tool_calls

        # 批次1：form_memory
        mock_form_memory = Mock()
        mock_form_memory.function.name = "form_memory"
        mock_form_memory.function.arguments = '{"reason": "test"}'
        mock_form_memory.id = "call_fm_cross"

        turn_tools: list[str] = []
        result1 = await handle_tool_calls(
            [mock_form_memory],
            todolist_skill_system,
            activated_skills={"todolist"},
            turn_tools=turn_tools,
        )
        assert "form_memory" in turn_tools

        # 批次2：todolist_check（应能检测到批次1的 form_memory）
        mock_tool_call = Mock()
        mock_tool_call.function.name = "todolist_check"
        mock_tool_call.function.arguments = '{"step": 1, "status": "done"}'
        mock_tool_call.id = "call_tl_cross"

        result2 = await handle_tool_calls(
            [mock_tool_call],
            todolist_skill_system,
            activated_skills={"todolist"},
            turn_tools=turn_tools,
        )

        data = json.loads(result2[0]["content"])
        assert data["success"] is True, f"跨批次 todolist_check 应通过，实际返回: {data}"
